#
# Created by  on 2020/10/10.
#
import re
from datetime import timedelta
from os.path import split, splitext, join

__all__ = [
    'treeview_sort_column',
    '_get_name_no_ext',
    '_validate_folder_path',
    '_get_size',
    '_check_range_acceptable',
    '_is_status_code_valid',
    '_fmt_dur_in_s',
    '_fmt_size',
]

from tkinter import TclError

from tkinter.ttk import Treeview


def treeview_sort_column(tv: Treeview, col, reverse):
    # https://stackoverflow.com/questions/1966929/tk-treeview-column-sort
    try:
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
    except TclError:  # col is display column (i.e. "#0") if TclError raised
        l = [(k, k) for k in tv.get_children('')]

    try:
        tmp = list(map(lambda t: (float(t[0]), t[1]), l))
        l = tmp
    except ValueError as e:
        pass

    l.sort(reverse=reverse)

    # rearrange items in sorted positions
    for index, (val, k) in enumerate(l):
        tv.move(k, '', index)

    # reverse sort next time
    tv.heading(col, command=lambda _col=col: treeview_sort_column(tv, _col, not reverse))


def _get_name_no_ext(path):
    return split(splitext(path)[0])[1]


def _validate_folder_path(folder_path):
    h, t = split(folder_path)
    t = re.sub(r"^ *|[. ]*$", "", t)
    return join(h, t)


def _get_size(response):
    try:
        return int(response.headers['Content-Length'])
    except KeyError:
        return None


def _check_range_acceptable(response):
    if response.status_code == 206:
        return True
    else:
        try:
            return response.headers['Accept-Ranges'] == 'bytes'
        except KeyError:
            return False


def _is_status_code_valid(code):
    d = code // 100
    return d in [1, 2, 3]


def _fmt_dur_in_s(dur: float, dp=2):
    try:
        whole, dec = str(timedelta(seconds=dur)).split('.')
        return whole + '.' + dec[:dp] if dp != 0 else whole
    except ValueError:
        return str(timedelta(seconds=dur))


def _fmt_size(s_in_bytes):
    # https://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB']:
        if abs(s_in_bytes) < 1024.0:
            return "%3.1f%s" % (s_in_bytes, unit)
        s_in_bytes /= 1024.0
    return "%.1f%s" % (s_in_bytes, 'YB')
