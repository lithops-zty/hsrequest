#
# Created by Lithops on 2020/10/27.
#
import bisect
import time
from tkinter import Tk, Label, Button
from typing import Dict, Callable, List, Optional


def _find_i_lt(a, x):
    """
    O(logn)
    https://docs.python.org/zh-cn/3.6/library/bisect.html
    :return the rightmost key that is earlier than timestamp.
    :raise ValueError if given timestamp is smaller than or equal to the smallest existing TimeKey.
    """
    i = bisect.bisect_left(a, x)
    if i:
        return i - 1
    else:
        raise ValueError


def _find_i_gt(a, x):
    i = bisect.bisect_right(a, x)
    if i != len(a):
        return i
    else:
        raise ValueError


def _find_i_le(a, x):
    i = bisect.bisect_right(a, x)
    if i:
        return i - 1
    else:
        raise ValueError


def _find_i_ge(a, x):
    i = bisect.bisect_left(a, x)
    if i:
        return i - 1
    else:
        raise ValueError


def _get_st_interval(v, interval):
    return v // interval * interval


def _get_time_ms() -> int:
    return int(time.time() * 1000)


class Stopwatch:
    """
    all time values are in ms.
    """
    STARTED = 'started'
    PAUSED = 'paused'

    class _Entry:
        def __init__(self, timestamp_ms, status, lapsed):
            self.ts = timestamp_ms
            self.status = status
            self.lapsed = lapsed

        def __hash__(self):
            return hash(self.ts)

        def __eq__(self, other):
            if isinstance(other, Stopwatch._Entry):
                return self.ts == other.ts
            raise TypeError

        def __repr__(self):
            return f'TimeKey(ts={self.ts}, status="{self.status}", lapsed={self.lapsed})'

        def __lt__(self, other):
            if isinstance(other, Stopwatch._Entry):
                return self.ts < other.ts
            elif isinstance(other, int):
                return self.ts < other
            raise TypeError

        def __gt__(self, other):
            if isinstance(other, Stopwatch._Entry):
                return self.ts > other.ts
            elif isinstance(other, int):
                return self.ts > other
            raise TypeError

    def __init__(self, start_now=True):
        self._records: List[Stopwatch._Entry] = []
        self.status = Stopwatch.PAUSED
        if start_now:
            self.start()

    def start(self):
        if self.status == self.STARTED:
            raise RuntimeError('stopwatch already started.')
        cur_t = _get_time_ms()
        try:
            last_item = self._records[-1]
            self._records.append(Stopwatch._Entry(cur_t, self.STARTED, last_item.lapsed))
        except IndexError:
            self._records.append(Stopwatch._Entry(cur_t, self.STARTED, 0))
        finally:
            self.status = self.STARTED

    def pause(self):
        if self.status == self.PAUSED:
            raise RuntimeError('stopwatch already paused.')
        cur_t = _get_time_ms()
        last_item = self._records[-1]
        self._records.append(Stopwatch._Entry(cur_t, self.PAUSED, last_item.lapsed + cur_t - last_item.ts))
        self.status = self.PAUSED

    def get_lapsed(self, timestamp_l, timestamp_u, *, no_error=False):
        if no_error:
            if timestamp_u > _get_time_ms():
                timestamp_u = _get_time_ms()
            if timestamp_l < self.initial_start_time():
                timestamp_l = self.initial_start_time()
            if timestamp_l > timestamp_u:
                timestamp_u = timestamp_l
        else:
            if timestamp_u > _get_time_ms():
                raise ValueError('this widget cannot predict the future :(')
            if timestamp_l < self.initial_start_time():
                raise ValueError('given timestamp is before the initial start of this Stopwatch.')
            if timestamp_l > timestamp_u:
                raise ValueError('lower bound should not be greater than upper bound.')

        # |-----------|~~~~~~~~~~|---|~~~~~~|------------------------|~~~~|-------|~~~~~~~~~~~|
        #  ---^                              ----------------^
        il = _find_i_le(self._records, timestamp_l)
        iu = _find_i_le(self._records, timestamp_u)
        entryl = self._records[il]
        entryu = self._records[iu]
        tl = entryl.lapsed + (0 if entryl.status == self.PAUSED else timestamp_l - entryl.ts)
        tu = entryu.lapsed + (0 if entryu.status == self.PAUSED else timestamp_u - entryu.ts)
        return tu - tl

    def initial_start_time(self):
        assert self._records[0].status == self.STARTED
        return self._records[0].ts

    def total_lapsed(self):
        cur_time = _get_time_ms()
        return self.get_lapsed(self.initial_start_time(), cur_time)

    def status_at(self, timestamp):
        interval_i = _find_i_le(self._records, timestamp)
        return self._records[interval_i].status

    def is_started_at(self, timestamp):
        return self.status_at(timestamp) == self.STARTED

    def __repr__(self):
        return 'Stopwatch:' + repr(self._records)


class Speedometer:
    """
    all time values are in ms
    """
    class _TimeKey:  # do not mix this class with int as keys of one dict.

        def __init__(self, timestamp_ms: int, precision_ms: int):
            self.timestamp = timestamp_ms
            self.precision = precision_ms
            self.st_interval = _get_st_interval(self.timestamp, self.precision)

        def __eq__(self, other):
            if isinstance(other, Speedometer._TimeKey):
                return self.st_interval == other.st_interval
            elif isinstance(other, int):
                return self.st_interval == _get_st_interval(other, self.precision)
            return False

        def __hash__(self):
            return hash(self.st_interval)

        def __repr__(self):
            return f'TimeKey(ts={self.timestamp}, p={self.precision}, st={self.st_interval})'

        def __lt__(self, other):
            if isinstance(other, Speedometer._TimeKey):
                return self.st_interval < other.st_interval
            elif isinstance(other, int):
                return self.st_interval < _get_st_interval(other, self.precision)
            raise TypeError

        def __gt__(self, other):
            if isinstance(other, Speedometer._TimeKey):
                return self.st_interval > other.st_interval
            elif isinstance(other, int):
                return self.st_interval > _get_st_interval(other, self.precision)
            raise TypeError

    def __init__(self, precision_ms=100, start_now=True):
        self.precision = precision_ms
        self._records: Dict[Speedometer._TimeKey, int] = {}  # suffix array
        self._sorted_keys = []
        self.stopwatch = Stopwatch(start_now=start_now)

    def _find_k_lt(self, timestamp):
        return self._sorted_keys[_find_i_lt(self._sorted_keys, timestamp)]

    def _find_v_lt(self, timestamp, earliest_v=None):
        try:
            return self._records[self._find_k_lt(timestamp)]
        except ValueError:
            if earliest_v is not None:
                return earliest_v
            raise

    def _find_k_gt(self, timestamp):
        return self._sorted_keys[_find_i_gt(self._sorted_keys, timestamp)]

    def _find_v_gt(self, timestamp, latest_v=None):
        try:
            return self._records[self._find_k_gt(timestamp)]
        except ValueError:
            if latest_v is not None:
                return latest_v
            raise

    def _find_k_le(self, timestamp):
        return self._sorted_keys[_find_i_le(self._sorted_keys, timestamp)]

    def _find_v_le(self, timestamp, earliest_v=None):
        try:
            return self._records[self._find_k_le(timestamp)]
        except ValueError:
            if earliest_v is not None:
                return earliest_v
            raise

    def _find_k_ge(self, timestamp):
        return self._sorted_keys[_find_i_ge(self._sorted_keys, timestamp)]

    def _find_v_ge(self, timestamp, latest_v=None):
        try:
            return self._records[self._find_k_ge(timestamp)]
        except ValueError:
            return latest_v

    def _gen_all_k_gt(self, timestamp):
        """
        O(nlogn)
        """
        while True:
            try:
                yield (timestamp := self._find_k_gt(timestamp))
            except ValueError:
                break

    def _gen_all_k_gt_2(self, timestamp):
        """
        O(n)
        """
        try:
            initial_i = _find_i_gt(self._sorted_keys, timestamp)
        except ValueError:
            return
        for i in range(initial_i, len(self._sorted_keys)):
            yield self._sorted_keys[i]

    def submit(self, value, timestamp=None, cumulative=False):
        """
        :param value: value to be submitted.
        :param timestamp: for debug use only.
        :param cumulative: if set to True, assume that the provided value is accumulated from the previous record.
        :return: True if the given value is inserted,
        False if the given value overwrote a previously inserted record.
        """

        if timestamp is None:  # O(1)? if timestamp not specified and insert to the end
            timestamp = _get_time_ms()
            if not self.stopwatch.is_started_at(timestamp):
                raise ValueError('submitting value when Speedometer is paused is disallowed.')
            k = Speedometer._TimeKey(timestamp, self.precision)
            is_overwritten = timestamp in self._records
            if not cumulative:
                if is_overwritten:
                    self._records[k] += value
                else:
                    prev_v = list(self._records.values())[-1] if len(self._records) > 0 else 0
                    self._records[k] = prev_v + value
            else:
                self._records[k] = value

            self._sorted_keys.append(k)

        else:  # O(logn) ? if timestamp specified and insertion point may not be the end
            if not self.stopwatch.is_started_at(timestamp):
                raise ValueError('submitting value when Speedometer is paused is disallowed.')
            k = Speedometer._TimeKey(timestamp, self.precision)
            is_overwritten = timestamp in self._records
            if not cumulative:
                if is_overwritten:
                    self._records[k] += value
                else:
                    prev_v = self._find_v_lt(timestamp, 0)
                    self._records[k] = prev_v + value
            else:
                self._records[k] = value

            # update sorted_keys
            self._sorted_keys.append(k)
            self._sorted_keys = sorted(self._sorted_keys)

            # update all later values if submitted timestamp is not the last.
            for k in self._gen_all_k_gt_2(timestamp):
                self._records[k] += value

        return is_overwritten

    def _get_value_between(self, timestamp_l, timestamp_u):
        vl = self._find_v_le(timestamp_l, 0)
        vu = self._find_v_le(timestamp_u, 0)
        return vu - vl

    def cur_speed(self, instant_ms=None, formatter: Optional[Callable[[float], str]] = None):
        if instant_ms is None:
            instant_ms = self.precision * 40  # default
        cur_time = _get_time_ms()
        delta_v = self._get_value_between(cur_time - instant_ms, cur_time)
        lapsed_time = self.stopwatch.get_lapsed(cur_time - instant_ms, cur_time, no_error=True)
        return formatter(delta_v / lapsed_time) if formatter is not None else delta_v / lapsed_time

    def overall_speed(self, formatter: Optional[Callable[[float], str]] = None):
        """

        :param formatter:
        :return: in v/ms
        """
        cur_time = _get_time_ms()
        delta_v = self._get_value_between(0, cur_time)
        lapsed_time = self.stopwatch.total_lapsed()  # todo
        return formatter(delta_v / lapsed_time) if formatter is not None else delta_v / lapsed_time

    def pause(self):
        self.stopwatch.pause()

    def start(self):
        self.stopwatch.start()

    def __repr__(self):
        return 'Speedometer:' + repr(self._records)


# 11003 True
# 12000 False
# 13043 True


#####test
#
# sm = Speedometer(precision_ms=50)
#
# sm.submit(3, 1000)
# sm.submit(9, 1050)
# sm.submit(3, 2050)
# sm.submit(9, 2300)
# sm.submit(8, 1900)
# sm.submit(8, 900)
#
# # 8 900
# # 11 1000
# # 20 1050
# # 28 1900
# # 31 2050
# # 40 2300
# while True:
#     st = int(input())
#     for i in sm._gen_all_k_gt(st):
#         print(i)
#     print('###########')
#     for i in sm._gen_all_k_gt_2(st):
#         print(i)
#     print()

import threading
from utils import _fmt_size
from random import randint
from time import sleep


def test1():
    def sp_fmt(sp):
        return _fmt_size(sp * 1000) + '/s'

    sm = Speedometer(100)

    def w():
        prog=0
        while True:
            # sleep(uniform(0, 1))
            # prog = randint(200 * 1024, 2000 * 1024)
            # sm.submit(prog)
            sleep(0.5)
            prog = 1024 * 1024 * 1.8
            t = sm.submit(prog, cumulative=False)
            if t:
                print(_get_time_ms() / 1000)

    def fff():
        print(sm)

    threading.Thread(target=w).start()

    root = Tk()
    l = Label(root)
    l.pack()
    btn = Button(root, command=fff, text='print')
    btn.pack()

    def show():
        l['text'] = sm.cur_speed(2000, formatter=sp_fmt)
        root.after(500, show)

    root.after(500, show)
    root.mainloop()


def test1_1():
    sm = Speedometer(precision_ms=50)

    sm.submit(3, 1000)
    sm.submit(9, 1050)
    sm.submit(3, 2050)
    sm.submit(9, 2300)
    sm.submit(8, 1900)
    sm.submit(8, 900)

    # 8 900
    # 11 1000
    # 20 1050
    # 28 1900
    # 31 2050
    # 40 2300
    while True:
        st = int(input())
        for i in sm._gen_all_k_gt(st):
            print(i)
        print('###########')
        for i in sm._gen_all_k_gt_2(st):
            print(i)
        print()


def test2():
    root = Tk()
    sw = Stopwatch(True)
    lbl_lapsed = Label(root)
    lbl_lapsed.pack()
    btn_stop = Button(root, text='stop', command=lambda: sw.pause())
    btn_start = Button(root, text='start', command=lambda: sw.start())
    btn_show = Button(root, text='show', command=lambda: print(sw))
    btn_lapse = Button(root, text='get lapsed', command=lambda: print(sw.total_lapsed()))
    btn_start.pack()
    btn_stop.pack()
    btn_show.pack()
    btn_lapse.pack()

    def f():
        ...
        lbl_lapsed['text'] = '%.03fs' % (sw.total_lapsed() / 1000)
        root.after(10, f)

    root.after(10, f)
    root.mainloop()


def test3():
    sw = Stopwatch(False)

    sw._records.append(sw._Entry(10, sw.STARTED, 0))
    sw._records.append(sw._Entry(80, sw.PAUSED, 70))
    sw._records.append(sw._Entry(100, sw.STARTED, 70))
    sw._records.append(sw._Entry(120, sw.PAUSED, 90))
    sw._records.append(sw._Entry(180, sw.STARTED, 90))
    sw._records.append(sw._Entry(200, sw.PAUSED, 110))
    sw._records.append(sw._Entry(290, sw.STARTED, 110))
    sw._records.append(sw._Entry(400, sw.PAUSED, 220))

    # |----------|~~~~|----|~~~~~~~~~|-----|~~~~~~~~~~~~~~~~~|-------------------------------------|
    # 10         80  100  120       180   200               290                                   400

    while True:
        a, b = map(int, input().split(' '))
        print(sw.get_lapsed(a, b))


if __name__ == '__main__':
    test1()
