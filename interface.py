#
# Created by Lithops on 2020/10/4.
#
from __future__ import annotations

from functools import wraps
from time import time
from tkinter import *
from tkinter.ttk import Separator, Treeview, Style
from typing import Dict, AnyStr, List

from Speedometer import Speedometer
from utils import *


def _timeit(func):  # for debug use
    def wrapper(*args, **kwargs):
        start = time()
        ret = func(*args, **kwargs)
        end = time()
        print(f'{func.__name__:<25} execution time: {_fmt_dur_in_s(end - start, dp=4)}')
        return ret

    # return wrapper
    return func


class Interface(Tk):
    class MultiProgressBar(Canvas):
        HIGHLIGHT_COLOR = '#34cf17'
        NORMAL_COLOR = '#008844'

        # FINISHED_COLOR = '#026131'

        class ToolTip(object):
            # https://stackoverflow.com/questions/3221956/how-do-i-display-tooltips-in-tkinter
            """
            create a tooltip for a given widget
            """

            # if tag specified and widget is Canvas, bind
            def __init__(self, widget, tag=None, text='widget info'):
                self.waittime = 300  # milliseconds
                self.wraplength = 180  # pixels
                self.widget: Widget = widget
                self.text = text

                if tag:
                    if not isinstance(widget, Canvas):
                        raise TypeError
                    self.widget.tag_bind(tag, "<Enter>", self.enter, add=True)
                    self.widget.tag_bind(tag, "<Leave>", self.leave, add=True)
                    self.widget.tag_bind(tag, "<ButtonPress>", self.leave, add=True)
                    self.widget.tag_bind(tag, "<Motion>", self.move, add=True)
                else:
                    self.widget.bind("<Enter>", self.enter)
                    self.widget.bind("<Leave>", self.leave)
                    self.widget.bind("<ButtonPress>", self.leave)
                    self.widget.bind("<Motion>", self.move)
                self.id = None
                self.tw = None

            def move(self, event=None):
                x, y = self.widget.winfo_pointerxy()
                y -= 30
                x -= 10
                if self.tw:
                    self.tw.wm_geometry("+%d+%d" % (x, y))

            def enter(self, event=None):
                self.schedule()

            def leave(self, event=None):
                self.unschedule()
                self.hidetip()

            def schedule(self):
                self.unschedule()
                self.id = self.widget.after(self.waittime, self.showtip)

            def unschedule(self):
                id = self.id
                self.id = None
                if id:
                    self.widget.after_cancel(id)

            def showtip(self, event=None):
                x, y = self.widget.winfo_pointerxy()
                y -= 30
                x -= 10
                # creates a toplevel window
                self.tw = Toplevel(self.widget)
                # Leaves only the label and removes the app window
                self.tw.wm_overrideredirect(True)
                self.tw.wm_geometry("+%d+%d" % (x, y))
                label = Label(self.tw, text=self.text, justify='left',
                              background="#ffffff", relief='solid', borderwidth=1,
                              wraplength=self.wraplength)
                label.pack(ipadx=1)

            def hidetip(self):
                tw = self.tw
                self.tw = None
                if tw:
                    tw.destroy()

        def __init__(self, size, master=None, bg='white', height='23', width=None, **kwargs):
            super().__init__(master=master, bg=bg, height=height, width=width, **kwargs)
            self.tooltip = None
            self.bind('<Configure>', self._on_resize)
            self.size = size

            # used to store old dimensions
            self.w = self.winfo_width()
            self.h = self.winfo_height()

            self.manager: Dict[
                AnyStr, List[List[int, int, int]]] = {}  # stack-like, {label: [[rect_id, from, to],...],...}

        def _on_resize(self, event):
            w_scale = event.width / self.w
            h_scale = event.height / self.h
            self.scale(ALL, 0, 0, w_scale, h_scale)
            # update dimensions
            self.w = event.width
            self.h = event.height

        # Conclude the progress of a rect
        def finalise(self, label):
            if label in self.manager:
                ended_rect = self.manager[label][-1][0]
                self.itemconfig(ended_rect, stipple='')

        def start(self, label, pos):
            self.finalise(label)

            w = self.winfo_width()
            h = self.winfo_height()

            xl = int(pos / self.size * w)
            xl = int(pos / self.size * w)
            yt = 0
            xr = xl
            yb = h

            new_rect = self.create_rectangle(xl, yt, xr, yb, fill=self.NORMAL_COLOR, outline='', tag=label,
                                             stipple='gray50')

            self.tag_bind(new_rect, '<Enter>', self.on_hover)
            self.tag_bind(new_rect, '<Leave>', self.on_leave)
            self.ToolTip(self, new_rect, label)

            self.create_line(xl, yt, xr, yb, fill='black')

            if label not in self.manager:
                self.manager[label] = [[new_rect, pos, pos]]  # create new stack
            else:
                self.manager[label].append([new_rect, pos, pos])  # push to stack

        def progress(self, label, amount):
            if label not in self.manager:
                raise KeyError

            cur_rect = self.manager[label][-1][0]
            self.manager[label][-1][2] += amount

            w = self.winfo_width()
            xl, yt, xr, yb = self.coords(cur_rect)
            if xr == int(self.manager[label][-1][2] / self.size * w):
                return
            xr = int(self.manager[label][-1][2] / self.size * w)

            self.coords(cur_rect, xl, yt, xr, yb)

        def on_hover(self, event=None):
            # getting the label needs much tweaks
            item = self.find_withtag(CURRENT)[0]
            label = self.gettags(item)[0]
            self.highlight(label)

        def on_leave(self, event=None):
            # getting the label needs much tweaks
            item = self.find_withtag(CURRENT)[0]
            label = self.gettags(item)[0]
            self.de_highlight(label)

        def change_color(self, label, color):
            if label not in self.manager:
                # raise KeyError(f'label "{label}" is not in rect_manager.')  # muted in V4.2
                return

            for each in self.manager[label]:
                self.itemconfig(each[0], fill=color)

        def highlight(self, label):
            self.change_color(label, self.HIGHLIGHT_COLOR)

        def de_highlight(self, label):
            self.change_color(label, self.NORMAL_COLOR)

    class InfoEntry(Frame):
        def __init__(self, key, value=None, *args, **kwargs):
            super().__init__(*args, **kwargs)

            # self.config(borderwidth=1, relief=GROOVE)
            self.columnconfigure(0, weight=0, minsize=120)
            self.columnconfigure(1, weight=0, minsize=10)
            self.columnconfigure(2, weight=1, minsize=300)
            self.rowconfigure(0, minsize=23)
            # self.rowconfigure(1, weight )

            self.key = Label(self, text=key)
            self.key.grid(sticky='e', padx=5, row=0, column=0)
            self.colon = Label(self, text=':')
            self.colon.grid(row=0, column=1)
            self.value = Label(self, text=value)
            self.value.grid(sticky='ew', padx=5, row=0, column=2)

            self.separator = Separator(self, orient=HORIZONTAL)
            self.separator.grid(row=1, column=0, columnspan=3, sticky='ew', padx=20)

        def set(self, value):
            self.value['text'] = value

    class ScrollableFrame(LabelFrame):
        RESIZE_FREQUENCY = 0

        def on_inner_frame_config(self, event):
            self.cvs.configure(scrollregion=self.cvs.bbox(ALL))
            _, yt, _, yb = self.cvs.bbox(ALL)
            self.max_height = yb - yt

        # def on_canvas_config(self, event):
        #     self.frm_inner.configure(height=event.height, width=event.width)

        def on_hover_bottom(self, event):
            self.configure(cursor='sb_v_double_arrow')

        def on_leave_bottom(self, event):
            self.configure(cursor='arrow')

        def on_drag_bottom(self, event):
            if time() * 1000 - self.last_resize_ms < self.RESIZE_FREQUENCY:
                return
            # xl, yt, xr, yb = self.winfo_x
            new_height = event.y_root - self.winfo_rooty() - (self.winfo_height() - self.cvs.winfo_height())
            new_height = min(new_height, self.max_height)
            self.cvs.configure(height=new_height)
            self.last_resize_ms = time() * 1000

        def on_mousewheel(self, event):
            self.cvs.yview_scroll(int(event.delta / -100), "units")

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            # set scrollable
            self.columnconfigure(0, weight=1)
            self.columnconfigure(1, weight=0)

            self.cvs = Canvas(self)
            self.cvs.grid(row=0, column=0, sticky='nswe')

            self.frm_inner = Frame(self.cvs)
            # self.frm_inner.pack_propagate(0)

            self.cvs.create_window((0, 0), window=self.frm_inner, anchor='nw')
            # self.cvs.bind('<Configure>', self.on_canvas_config)
            self.scrb = Scrollbar(self, command=self.cvs.yview)
            self.scrb.grid(row=0, column=1, rowspan=2, sticky='nswe')

            self.cvs.configure(yscrollcommand=self.scrb.set, height=self.frm_inner.winfo_height())

            self.frm_inner.bind("<Configure>", self.on_inner_frame_config)
            self.cvs.bind_all('<MouseWheel>', self.on_mousewheel)
            # set resizable
            self.max_height = self.winfo_height()

            self.btm_line = Frame(self)
            self.btm_line.grid(row=1, column=0, columnspan=1, sticky='ewns', ipady=5)
            self.btm_line.bind('<Enter>', self.on_hover_bottom)
            self.btm_line.bind('<Leave>', self.on_leave_bottom)

            self.btm_line.bind('<B1-Motion>', self.on_drag_bottom)
            # control resize frequency
            self.last_resize_ms = time() * 1000

        def get_master(self):
            return self.frm_inner

        def update(self):
            super().update()
            self.cvs.configure(height=self.frm_inner.winfo_height())

    class AutoExpandText(Text):
        LAG_TIME = 400  # ms

        def on_hover(self, event=None):
            if self.index(f'@0,{self.winfo_height()}') == self.index('end-1c'):
                return  # if every character is visible
            self.schedule()

        def monitor_cursor_pos(self):
            self.after(1000, self.monitor_cursor_pos)
            if self.tw is None:
                return
            self.tw.update()
            xl = self.tw.winfo_rootx()
            yt = self.tw.winfo_rooty()
            xr = xl + self.tw.winfo_width()
            yb = yt + self.tw.winfo_height()
            cur_x, cur_y = self.winfo_pointerxy()
            if xl <= cur_x <= xr and yt <= cur_y <= yb:
                return  # if cursor is inside the expanded window, do nothing
            self.unschedule()
            self.collapse()

        def schedule(self):
            self.unschedule()
            self.id = self.after(self.LAG_TIME, self.expand())

        def unschedule(self):
            if self.id:
                self.after_cancel(self.id)
                self.id = None

        def expand(self):
            if self.tw:
                self.collapse()

            x = self.winfo_rootx()
            y = self.winfo_rooty()
            self.tw = Toplevel(self)
            self.tw.wm_overrideredirect(True)
            self.tw.wm_geometry("+%d+%d" % (x, y))
            self.tw.config(width=self.winfo_width())

            txt = Text(self.tw)
            txt.pack(fill=BOTH)
            txt.insert(1.0, self.get(1.0, END))
            for key in self.configure():
                txt.configure({key: self.cget(key)})
            txt.config(height=int(self.count(1.0, END, 'displaylines')[0]),
                       borderwidth=1,
                       relief=SOLID,
                       state=DISABLED)

        def collapse(self):
            if self.tw:
                self.tw.destroy()
                self.tw = None

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.id = None
            self.tw: Toplevel = None
            self.bind('<Enter>', self.on_hover, add=True)
            self.after(0,
                       self.monitor_cursor_pos)  # after is used instead of Leave because Leave event may not be caught due to lag time.

    info_keylist = [
        # 'headers',
        'size',
        'downloaded',
        'current speed',
        'average speed',
        'time used',
        'time left'
    ]

    chart_labels = [
        'ID',
        'Speed',
        'Downloaded Size',
        'Status'
    ]

    column_widths_w = [
        1,
        2,
        2,
        3
    ]

    # def after(self, ms, func=None, *args):
    #     ret = super().after(ms, func=func, *args)
    #     self.after_ids[func.__name__] = ret
    #     return ret
    #
    # def destroy(self):
    #     super().destroy()
    #     for each in self.after_ids:
    #         self.after_cancel(self.after_ids[each])

    # draw interface
    def __init__(self, url, headers, path, size, **kwargs):
        super().__init__(**kwargs)

        self.url = url
        self.headers = headers
        self.path = path
        self.size = size
        self.downloaded_sizes: Dict[AnyStr, int] = {}  # downloaded sizes of respective threads
        self.total_downloaded = 0
        self.speedometers: Dict[AnyStr, Speedometer] = {}
        self.cached_current_speeds = {}  # cache data from speedometers

        self.statuses: Dict[AnyStr, AnyStr] = {}
        self.start_time = time()
        self.registered_labels = []

        # self.after_ids = {}

        self.title('Downloader')
        self.geometry('500x600+300+50')
        self.columnconfigure(0, weight=1)
        self.resizable(False, False)

        ##########
        Label(self, text='Downloading').grid(padx=15, pady=(10, 0), sticky='w')

        self.txt_url = self.AutoExpandText(self, cursor='arrow', padx=5, pady=3, height=1)
        self.txt_url.grid(padx=15, pady=5, sticky='ew')
        self.txt_url.insert(1.0, self.url)
        self.txt_url.config(state=DISABLED)

        Label(self, text='to').grid(padx=15, pady=0, sticky='w')

        self.txt_path = self.AutoExpandText(self, cursor='arrow', padx=5, pady=3, height=1)
        self.txt_path.grid(padx=15, pady=(3, 5), sticky='ew')
        self.txt_path.insert(1.0, self.path)
        self.txt_path.config(state=DISABLED)

        ###########
        self.frm_info = self.ScrollableFrame(self, text='Information', borderwidth=3, relief=GROOVE)

        self.frm_info.grid(sticky='ew', padx=15, pady=(5, 0))

        self.lbls_info = {}
        for key in self.info_keylist:
            tmp = self.InfoEntry(key, None, master=self.frm_info.get_master())
            tmp.pack(fill=X)
            self.lbls_info[key] = tmp
        self.frm_info.update()

        ############
        Label(self, text='Progress:').grid(sticky='w', padx=18)
        self.bar = self.MultiProgressBar(self.size, self, borderwidth=1, relief=SUNKEN)
        self.bar.grid(sticky='ew', padx=13)
        self.bar.update()  # todo: why need this??

        ############  todo  make this shitty block of code look better
        frm = Frame(self, height=200, borderwidth=3, relief=GROOVE)
        frm.grid(padx=15, pady=5, row=7, sticky='nsew')
        frm.update()
        Style(frm).configure('Treeview', rowheight=20)
        self.chart = Treeview(frm, columns=self.chart_labels[1:])
        self.chart.place(x=0, y=0, relheight=1, width=frm.winfo_width() - 18)
        sb = Scrollbar(frm, command=self.chart.yview)
        sb.place(x=frm.winfo_width() - 22, y=0, relheight=1, width=16)
        self.chart.config(yscrollcommand=sb.set)
        self.chart.update()

        total_w = sum(self.column_widths_w)
        for i, label in enumerate(self.chart_labels):
            self.chart.column(f'#{i}',
                              width=int((frm.winfo_width() - sb.winfo_width()) / total_w * self.column_widths_w[i]),
                              anchor=CENTER)
            self.chart.heading(f'#{i}', text=label,
                               command=lambda col=f'#{i}': treeview_sort_column(self.chart, col, False))
            # Note: command=lambda _x=x: func(_x) is not equivalent to command=lambda: func(x).
            # see https://stackoverflow.com/questions/1966929/tk-treeview-column-sort

        ############ todo until here.
        # add events to chart
        def on_hover(event=None):
            iid = self.chart.identify_row(event.y)
            for each in self.chart.selection():
                self.bar.de_highlight(each)
            self.chart.selection_remove(self.chart.selection())
            if iid != '':
                self.chart.selection_add(iid)
                self.bar.highlight(iid)

        self.chart.bind('<Motion>', on_hover)

        ############## register updates
        self.after(0, self._update_total_size)
        self.after(0, self._update_downloaded_size)
        self.after(0, self._update_total_current_speed)
        self.after(0, self._update_average_speed)
        self.after(0, self._update_time_used)
        self.after(0, self._update_time_left)
        self.after(0, self._cache_current_speeds)
        self.after(0, self._update_chart)

    # a decorator registering new labels passed in
    # https://stackoverflow.com/questions/47953245/decorator-inside-a-class-throw-warning-in-pycharm
    def _register_label(func):
        @wraps(func)
        # def wrapper(self: >>Interface<<, label, *args, **kwargs):
        # https://stackoverflow.com/questions/33533148/how-do-i-type-hint-a-method-with-the-type-of-the-enclosing-class
        def wrapper(self: Interface, label, *args, **kwargs):
            if label not in self.registered_labels:
                self.registered_labels.append(label)
            return func(self, label, *args, **kwargs)

        return wrapper

    # a decorator re-registering the decorated function to Tk.
    def _circular_call(ms, pos):
        if pos not in ['bef', 'aft']:
            raise ValueError('pos must be either "bef" or "aft". ')

        def decorator(func):
            @wraps(func)
            def wrapper(self: Tk, *args, **kwargs):
                if pos == 'bef':
                    self.after(ms, lambda args=args, kwargs=dict(kwargs): wrapper(self, *args, **kwargs))
                ret = func(self, *args, **kwargs)
                if pos == 'aft':
                    self.after(ms, lambda args=args, kwargs=dict(kwargs): wrapper(self, *args, **kwargs))
                return ret

            return wrapper

        return decorator

    def _update_total_size(self):
        self.lbls_info['size'].set(_fmt_size(self.size))

    @_circular_call(500, 'bef')
    @_timeit
    def _update_downloaded_size(self):
        self.lbls_info['downloaded'].set(
            f'{_fmt_size(self.total_downloaded)} ({self.total_downloaded / self.size * 100:.2f}%)')

    @_circular_call(500, 'bef')
    @_timeit
    def _update_total_current_speed(self):
        total_current_speed = sum(self.cached_current_speeds.values()) * 1000
        self.lbls_info['current speed'].set(_fmt_size(total_current_speed) + '/s')

    @_circular_call(500, 'bef')
    @_timeit
    def _update_average_speed(self):
        if time() == self.start_time:
            return  # avoid zero division
        ave_speed = self.total_downloaded / (time() - self.start_time)
        self.lbls_info['average speed'].set(_fmt_size(ave_speed) + '/s')

    @_circular_call(1000, 'bef')
    @_timeit
    def _update_time_used(self):
        if time() == self.start_time:
            return  # avoid zero division
        self.lbls_info['time used'].set(f'{_fmt_dur_in_s(time() - self.start_time, dp=0)}')

    @_circular_call(500, 'bef')
    @_timeit
    def _update_time_left(self):
        total_current_speed = sum(self.cached_current_speeds.values()) * 1000
        if total_current_speed == 0:
            return
        time_left = (self.size - self.total_downloaded) / total_current_speed
        self.lbls_info['time left'].set(_fmt_dur_in_s(time_left))

    @_circular_call(500, 'bef')
    @_timeit
    def _cache_current_speeds(self):
        for label in self.speedometers:
            self.cached_current_speeds[label] = self.speedometers[label].cur_speed(instant_ms=1973)

    @_circular_call(500, 'bef')
    @_timeit
    def _update_chart(self):
        for label in self.registered_labels:
            if label not in self.chart.get_children(''):
                self.chart.insert('', END, iid=label, text=label)
            try:
                self.chart.set(label, 'Speed', _fmt_size(self.cached_current_speeds[label] * 1000) + '/s')
            except KeyError:
                pass
            try:
                self.chart.set(label, 'Downloaded Size', _fmt_size(self.downloaded_sizes[label]))
            except KeyError:
                pass
            try:
                self.chart.set(label, 'Status', self.statuses[label])
            except KeyError:
                pass

    @_register_label
    @_timeit
    def start(self, label, pos):
        if label not in self.downloaded_sizes:
            self.downloaded_sizes[label] = 0
        if label not in self.speedometers:
            self.speedometers[label] = Speedometer(precision_ms=50)

        self.bar.start(label, pos)

    @_timeit
    def progress(self, label, amount):  # todo make this function O(1), or the interface lags like shit. (done.)
        self.downloaded_sizes[label] += amount
        self.total_downloaded += amount

        self.bar.progress(label, amount)

        self.speedometers[label].submit(amount, cumulative=False)
        # self.speedometers[label].submit(self.downloaded_sizes[label], cumulative=True)

    @_register_label
    @_timeit
    def finalise(self, label):
        self.bar.finalise(label)

    @_register_label
    @_timeit
    def submit_status(self, label, status):
        self.statuses[label] = status

    # @_register_label
    # def submit_speed(self, label, speed):
    #     self.speeds[label] = speed


if __name__ == '__main__':
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:56.0) Gecko/20100101 Firefox/56.0',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        # 'Range': 'bytes=0-', # v2: now it is auto-included.
        'Referer': 'https://www.bilibili.com',
        'Origin': 'https://www.bilibili.com',
        'Connection': 'keep-alive',
    }

    root = Interface(
        'http://upos-sz-mirrorks3.bilivideo.com/upgcxcode/84/87/52498784/52498784-1-80.flv?e=ig8euxZM2rNcNbuVhbUVhoMahwNBhwdEto8g5X10ugNcXBlqNxHxNEVE5XREto8KqJZHUa6m5J0SqE85tZvEuENvNo8g2ENvNo8i8o859r1qXg8xNEVE5XREto8GuFGv2U7SuxI72X6fTr859r1qXg8gNEVE5XREto8z5JZC2X2gkX5L5F1eTX1jkXlsTXHeux_f2o859IB_&uipk=5&nbs=1&deadline=1599559167&gen=playurl&os=ks3bv&oi=2028515290&trid=8e6727da260c40c8a578c7bf43c7be92u&platform=pc&upsig=b1a6fd41fa3fd96e51cc5bd1782203a3&uparams=e,uipk,nbs,deadline,gen,os,oi,trid,platform&mid=383905456&orderid=0,3&agrr=1&logo=80000000',
        headers,
        r'D:\Lithops',
        100)

    root.start('0', 40)
    root.progress('0', 10)

    root.start('1', 0)
    root.progress('1', 10)

    root.start('0', 90)
    root.progress('0', 10)

    root.mainloop()
