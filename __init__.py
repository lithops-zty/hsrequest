#
# Created by Lithops on 2020/10/18.
#


import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from os import listdir, makedirs
from os.path import join, exists, split
from random import randint, choice
from time import sleep, time
from typing import Optional

import requests

from interface import Interface
from utils import *

script_folder = split(__file__)[0]

logging.basicConfig(filename=join(script_folder, 'logging_info.txt'),
                    level=logging.DEBUG,
                    filemode='w',
                    format='%(module)-12s line=%(lineno)-5d %(levelname)-7s %(asctime)-10s %(message)s',
                    datefmt='%H:%M:%S')

# disable all other loggers - workaround that avoids requests module from writing to my logger file, finding which wasted a lot of my time.
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).disabled = True

_logger = logging.getLogger('hsrequest_logger')

_mutex = threading.Lock()

_local = threading.local()  # place to put thread-local data (i.e. private data owned by a single thread)


# [[start,end,ongoing],[start,end,ongoing]...]
# meaning: [start,end) has downloaded;
# ongoing==True: end may extend (download process for this chunk has not finished. Other threads should not start straight at end.
# ongoing==False: end will no longer extend (download process for this chunk has finished. Feel free to start right at end.
class _Progress(list):
    def ins(self, a):
        for i in range(len(self)):
            if a[0] < self[i][0]:
                self.insert(i, a)
                return
        self.insert(len(self), a)

    def get_next(self, a):
        return self[self.index(a) + 1]

    # find another point to start that has the biggest undownloaded span after thread finishes downloading
    # return -1: Stand by; -2: All finished; other non-neg values: pos to insert at.
    def find_insert_pt(self):
        code = -2
        pos = []
        for i in range(len(self) - 1):
            span = self[i + 1][0] - self[i][1]
            if code == -2 and span > 0:
                code = -1
            if self[i][2] and span > min_insertion_interval:
                pos.append((self[i + 1][0] + self[i][1]) // 2)
            elif not self[i][2] and span > 0:
                pos.append(self[i][1])
        print(pos)
        return choice(pos) if len(pos) != 0 else code


chunk_size = 40960  # size of each retrieval of data, in bytes
min_insertion_interval = 4096000  # minimum interval of undownloaded data that allows a thread to start downloading from, in bytes
# ^making this value too small leads to large volume of requests and too many debris files,
# thus taking more time for downloading & combining.
_progress = _Progress()
temp_dir = join(script_folder, 'temp_debris_st')  # directory to store all debris files

interface: Optional[Interface] = None

def _download_thread(debris_dir, url, size, start, no, headers, timeout, **kwargs):
    if start == -1:
        interface.submit_status(str(no), "Stand by.")
        interface.finalise(str(no))
        _logger.debug(f'thread {no}: Stand by.')
        if _mutex.locked():  # after some tests, this condition seems to be always true.
            _mutex.release()
        sleep(1)
    elif start == -2:
        interface.submit_status(str(no), "Execution over.")
        interface.finalise(str(no))
        _logger.debug(f'thread {no}: EXECUTION OVER.')
        if _mutex.locked():  # after some tests, this condition seems to be always true.
            _mutex.release()
        if hasattr(_local, 'session'):
            _local.session.close()
        return
    else:
        download_range = [start, start, True]
        _progress.ins(download_range)
        if _mutex.locked():
            _mutex.release()  # mark has set. release. be careful the lock should be released only when this function is recursively called.

        if not hasattr(_local, 'session'):
            session = requests.Session()
            _local.session = session
        else:
            session = _local.session

        debris_path = join(debris_dir, f'{start}')

        headers_copy = dict(headers)
        headers_copy['Range'] = f'bytes={start}-'

        _logger.debug(f'thread {no}: {start}- sending request...')

        try:
            interface.submit_status(str(no), 'Sending request...')
            html = session.request(url=url, headers=headers_copy, timeout=timeout, stream=True, **kwargs)
            it = html.iter_content(chunk_size=chunk_size)
            if not _is_status_code_valid(html.status_code):
                raise requests.RequestException(f'invalid response code = {html.status_code}.')
        except requests.RequestException as e:
            interface.submit_status(str(no), 'Get response failed')
            sleep(2)
            _logger.error(f'thread {no}: failed to get response: {e}')

            # goto find next position and recurse
        else:  # successfully opened request stream for retrieval by chunk
            _logger.debug(f'thread {no}: request success. response code = {html.status_code}')
            # _logger.debug(f'thread {no}: cookies = {session.cookies.get_dict()}')
            interface.submit_status(str(no), 'Retrieving...')
            interface.start(str(no), start)

            with open(debris_path, 'wb') as f:
                while True:
                    try:
                        data = next(it)
                    except (requests.RequestException, StopIteration) as e:
                        _logger.error(f'thread {no}: failed to get data: {e}')
                        interface.submit_status(str(no), 'Get data failed')
                        download_range[2] = False
                        sleep(2)
                        break  # goto find next position and recurse
                    with _mutex:
                        to_end = _progress.get_next(download_range)[0] - download_range[1]
                    if to_end <= len(data):  # expected to be chunk_size, but written as len(data) for safety.
                        download_range[1] += to_end
                        f.write(data[:to_end])
                        interface.progress(str(no), to_end)
                        break
                    else:
                        download_range[1] += len(
                            data)  # expected to be chunk_size, but written as len(data) for safety.
                        f.write(data)
                        interface.progress(str(no), len(data))

        _logger.debug(f'thread {no}: {start}-{download_range[1]} downloaded.')
        download_range[2] = False
        if download_range[0] == download_range[
            1]:  # if nothing is downloaded, remove entry from progress (otherwise it causes a bug - see log)
            with _mutex:
                _progress.remove(download_range)

    _mutex.acquire()  # lock until mark set in progress.
    next_start = _progress.find_insert_pt()
    _download_thread(debris_dir, url, size, next_start, no, headers, timeout, **kwargs)


def _merge_debris(debris_dir, final_path):
    with open(final_path, 'wb') as final:
        total_len = 0
        for d in sorted(listdir(debris_dir), key=lambda x: int(x.split('.')[0])):
            d = join(debris_dir, d)
            with open(d, 'rb') as debris:
                data = debris.read()
                total_len += len(data)
                final.write(data)
    return total_len


def _dispatch_download(file_path, url, size, thread_count, headers, timeout, **kwargs):
    _progress.clear()
    _progress.ins([size, size, False])
    _progress.ins([0, 0, False])

    makedirs(temp_dir, exist_ok=True)

    debris_dir = join(temp_dir, _get_name_no_ext(file_path))

    debris_dir = _validate_folder_path(
        debris_dir)  # strip leading & trailing spaces, and trailing periods, from folder name.

    if exists(debris_dir):
        shutil.rmtree(debris_dir)  # clean up first
    makedirs(debris_dir, exist_ok=True)
    makedirs(split(file_path)[0], exist_ok=True)

    pool = []
    for i in range(thread_count):
        pool.append(
            threading.Thread(target=_download_thread,
                             args=(
                                 debris_dir, url, size, size // thread_count * i, i, headers, timeout), kwargs=kwargs))

    ####### GUI
    global interface
    interface = Interface(url, headers, file_path, size)

    def shut_on_all_done():
        if any([th.is_alive() for th in pool]):
            interface.after(2000, shut_on_all_done)
            return
        interface.destroy()

    interface.after(0, shut_on_all_done)
    interface.protocol('WM_DELETE_WINDOW', lambda: '')
    for th in pool:
        th.start()

    interface.mainloop()

    # for th in pool:
    #     th.join()

    downloaded_size = _merge_debris(debris_dir, file_path)

    if downloaded_size != size:
        raise IOError(f'(downloaded size({downloaded_size}B) does not tally with the size given by server({size}B).')

    shutil.rmtree(debris_dir)


#########################################


# exposed interface
def download_with_progress(file_path, url, thread_count=min(32, os.cpu_count() + 4), headers=None, timeout=20,
                           raise_for_status=True, **kwargs):
    if timeout is None:
        raise ValueError('cannot have timeout unspecified due to download mechanism.')

    _logger.debug(f"thread main: START DOWNLOADING: '{_get_name_no_ext(file_path)}'. ")
    s_t = time()

    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.105 Safari/537.36'
        }

    ##################### start pre-check
    headers.pop('Range', None)

    headers_copy = dict(headers)
    headers_copy['Range'] = 'bytes=0-'
    # cannot add number after hyphen, or get_size() will not return the correct size of the whole content.

    # temprarily remove 'method' value from kwargs; if non-existent, default to 'GET'.
    method = kwargs.pop('method', 'GET')

    resp = requests.get(url, headers=headers_copy, timeout=timeout, stream=True, **kwargs)
    if raise_for_status:
        resp.raise_for_status()

    # add back
    kwargs['method'] = method

    total_size = _get_size(resp)
    if total_size is None:
        raise requests.RequestException('essential header "content-length" is not supported for this request.')

    if not _check_range_acceptable(resp):
        thread_count = 1

    # cap actual no of threads if content size is too small as compared to min_insertion_interval
    # but code works totally perfectly even without these two lines.
    if total_size / min_insertion_interval < thread_count:
        thread_count = ceil(total_size / min_insertion_interval)

    ##################### end pre-check

    _dispatch_download(file_path, url, total_size, thread_count, headers, timeout, **kwargs)
    e_t = time()
    dur = e_t - s_t
    _logger.debug(f"thread main: DOWNLOADING FINISHED IN {_fmt_dur_in_s(dur)}. ")


# temporarily no use
def get_responses(urls, headers_l=None, data_l=None, timeout=20, thread_count=7):
    if headers_l is None:
        headers_l = [{
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.105 Safari/537.36'
        }] * len(urls)
    if data_l is None:
        data_l = [None] * len(urls)

    with ThreadPoolExecutor(max_workers=thread_count) as exe:
        futures = []
        for url, headers, data in zip(urls, headers_l, data_l):
            futures.append(exe.submit(requests.get, url, headers=headers, data=data, timeout=timeout))

    results = []
    for each in futures:
        results.append(each.result())
    return results


if __name__ == '__main__':
    # url = 'https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png'
    # url = 'https://i0.hdslb.com/bfs/archive/622017dd4b0140432962d3ce0c6db99d77d2e937.png'
    # url = 'https://static.wikia.nocookie.net/terraria_gamepedia/images/3/36/Megashark.png/revision/latest/scale-to-width-down/70?cb=20200516215241'
    # url='http://upos-sz-mirrorkodo.bilivideo.com/upgcxcode/19/84/52498419/52498419-1-80.flv?e=ig8euxZM2rNcNbuVhbUVhoMahwNBhwdEto8g5X10ugNcXBlqNxHxNEVE5XREto8KqJZHUa6m5J0SqE85tZvEuENvNo8g2ENvNo8i8o859r1qXg8xNEVE5XREto8GuFGv2U7SuxI72X6fTr859r1qXg8gNEVE5XREto8z5JZC2X2gkX5L5F1eTX1jkXlsTXHeux_f2o859IB_&uipk=5&nbs=1&deadline=1599551470&gen=playurl&os=kodobv&oi=2028508781&trid=f2d4db6c31594cf9ad0b680b7342d7d6u&platform=pc&upsig=602012dd2ba224d62d5d11d0fc653605&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,platform&mid=383905456&orderid=0,3&agrr=0&logo=80000000'

    # url = "http://upos-sz-mirrorhw.bilivideo.com/upgcxcode/42/60/8076042/8076042_da3-1-80.flv?e=ig8euxZM2rNcNbU1hwdVhoMBhWdVhwdEto8g5X10ugNcXBlqNxHxNEVE5XREto8KqJZHUa6m5J0SqE85tZvEuENvNo8g2ENvNo8i8o859r1qXg8xNEVE5XREto8GuFGv2U7SuxI72X6fTr859r1qXg8gNEVE5XREto8z5JZC2X2gkX5L5F1eTX1jkXlsTXHeux_f2o859IB_&uipk=5&nbs=1&deadline=1604931999&gen=playurl&os=hwbv&oi=827385706&trid=e77005cc13e14eb89692a0eeecf2302du&platform=pc&upsig=9b04d8708dfd4df0d1ec749d0ba9b830&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,platform&mid=383905456&orderid=0,3&agrr=0&logo=80000000"
    # url = "https://upos-hz-mirrorakam.akamaized.net/upgcxcode/51/08/7220851/7220851_da8-1-32.flv?e=ig8euxZM2rNcNbRghbUVhoM1hbNBhwdEto8g5X10ugNcXBlqNxHxNEVE5XREto8KqJZHUa6m5J0SqE85tZvEuENvNo8g2ENvNo8i8o859r1qXg8xNEVE5XREto8GuFGv2U7SuxI72X6fTr859r1qXg8gNEVE5XREto8z5JZC2X2gkX5L5F1eTX1jkXlsTXHeux_f2o859IB_&uipk=5&nbs=1&deadline=1627183280&gen=playurlv2&os=akam&oi=3535870722&trid=876d539b556842d6b054b9154e28ffd0u&platform=pc&upsig=39ee1e2f2da4843c90ef6f2e97414e5f&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,platform&hdnts=exp=1627183280~hmac=6ff601cf5313cf8695c325464ffdda231ee9d514ccb69fc67739286d6a16d6c1&mid=383905456&bvc=vod&nettype=0&orderid=0,1&agrr=0&logo=80000000"
    url = "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_20mb.mp4"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:56.0) Gecko/20100101 Firefox/56.0',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        # 'Range': 'bytes=0-', # v2: now it is auto-included.
        # 'Referer': 'https://www.bilibili.com',
        # 'Origin': 'https://www.bilibili.com',
        'Connection': 'keep-alive',
    }
    download_with_progress(r'.\video.mp4', url, headers=headers, timeout=10, thread_count=6, method='GET')
