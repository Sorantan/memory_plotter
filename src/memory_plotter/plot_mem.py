from __future__ import annotations

import datetime
import functools
import os
import time
import traceback
from collections import deque
from enum import IntEnum, auto
from multiprocessing import Process, Queue, Value
from multiprocessing.sharedctypes import Synchronized
from typing import Callable, TypeVar

import matplotlib.pyplot as plt
import psutil
from typing_extensions import ParamSpec  # Before Python 3.10, this line is needed.

# Reference of realtime plot
# https://qiita.com/dendensho/items/79e9d2e3d4e8eb5061bc

WAITING_TIME = 0.1
# Intervals of refresh plot and get usage memory.
# ただし, グラフのプロット時間 + wait(WAITING_TIME) でループするので
# 厳密な時間ではなく, 少しずつ遅延する

HOLD_DATA_SIZE = 5000
# グラフをどれくらいの大きさに保持するか
# この大きさより長い場合, 古い方から消去される

class Status(IntEnum):
    WAITING_START = auto()
    """アプリケーションの起動待ち"""
    RUNNING = auto()
    """実行中"""
    STOP_PLOTTING = auto()
    """グラフの更新を停止する信号"""
    WAITING_STOP = auto()
    """終了待ち"""
    CLOSE_FIGURE = auto()
    """グラフを閉じる"""


UNIT = 1024**2

def memory_check(pid:int = os.getpid()) -> tuple[float, float, float]:
    """
    与えられたPIDの物理メモリと仮想メモリ使用量を返す。
    Windowsの場合は仮想メモリ=物理メモリ(共有部分を除く)+ページファイル
    """
    mem_info = psutil.Process(pid=pid).memory_info()
    pmem = mem_info.rss / UNIT # 物理メモリ
    vmem = mem_info.vms / UNIT # 仮想メモリ
    peak = mem_info.peak_pagefile / UNIT # 仮想メモリのこれまでの最大値
    return pmem, vmem, peak

def plotting(
        status: Synchronized[Status],
        pid: Synchronized[int],
        file_name: str | None = None):
    """グラフのプロット関数

    Parameters
    ----------
    status : Synchronized[Status]
        plotting 関数のステータス
    pid : Synchronized[int]
        Target Process ID
    file_name : str | None, optional
        File を出力するか, by default None
    """

    # 初期化
    times = deque([.0] * HOLD_DATA_SIZE, maxlen=HOLD_DATA_SIZE)
    pmems = deque([.0] * HOLD_DATA_SIZE, maxlen=HOLD_DATA_SIZE)
    vmems = deque([.0] * HOLD_DATA_SIZE, maxlen=HOLD_DATA_SIZE)
    peaks = deque([.0] * HOLD_DATA_SIZE, maxlen=HOLD_DATA_SIZE)

    plt.ion()
    plt.figure()
    li_p, = plt.plot(times, pmems, label='Physical')
    li_v, = plt.plot(times, vmems, label='Virtual')
    li_a, = plt.plot(times, peaks, label='Peak Virtual', linestyle='--')

    plt.legend()

    plt.xlabel('Time (s)')
    plt.ylabel('Used memory (MB)')
    plt.title('Memory Usage')
    plt.grid(True)

    if file_name is not None:  # ファイル出力開始
        f = open(file_name, 'w', encoding='utf-8')
        flush_count = 0

    try:
        if file_name is not None:
            f.write(f"StartTime: {str(datetime.datetime.now())}\n")
            f.write("Time,PhysicalMemory,VirtualMemory,PeakMemory\n")
            f.flush()

        start_time = time.time()
        # メインループ
        while True:
            if status.value == Status.WAITING_START: # アプリケーション起動待ち
                plt.pause(0.1)
                start_time = time.time()
            elif status.value == Status.RUNNING: # 実行中
                current_time = (time.time() - start_time) + WAITING_TIME
                try:
                    mem = memory_check(pid.value)
                except psutil.NoSuchProcess:
                    # 起動してプロセスを確認するまで偶にラグがあり,
                    # エラーが発生するのでここで回避する
                    continue

                if file_name is not None:
                    # ファイル出力
                    f.write(f"{current_time},{mem[0]},{mem[1]},{mem[2]}\n")
                    flush_count += 1
                    if flush_count == 10:
                        f.flush()
                        flush_count = 0
                times.append(current_time)
                pmems.append(mem[0])
                vmems.append(mem[1])
                peaks.append(mem[2])

                li_p.set_xdata(times)
                li_p.set_ydata(pmems)
                li_v.set_xdata(times)
                li_v.set_ydata(vmems)
                li_a.set_xdata(times)
                li_a.set_ydata(peaks)

                plt.xlim(times[0], times[-1])
                plt.ylim(0, peaks[-1]*1.1)
                plt.draw()

                plt.pause(WAITING_TIME)
            elif status.value == Status.STOP_PLOTTING: # Peak 時の値を Text で表示し, グラフの更新を停止する
                plt.text(times[-1], peaks[-1],
                         f'Peak Virtual Memory: {peaks[-1]:.3f} MB', ha='right')
                plt.ioff()
                if file_name is not None:
                    # ファイル出力の終了
                    f.close()
                status.value = Status.WAITING_STOP
            elif status.value == Status.WAITING_STOP: # 終了待ち
                plt.pause(0.1)
            elif status.value == Status.CLOSE_FIGURE: # グラフを閉じる
                plt.clf()
                plt.close()
                break
            else: # 異常値
                raise ValueError("Invalid Status")
    finally:
        if file_name is not None:
            f.close()
        plt.close()


R = TypeVar('R')
P = ParamSpec('P')

def local_func(
        __func: Callable[P, R], __q: Queue,
        *args: P.args, **kwargs: P.kwargs):
    result = None
    try:
        result = __func(*args, **kwargs)
    except Exception:
        print(traceback.format_exc())
    __q.put(result)

def realtime_mem_plot(
        func: Callable[P, R],
        file_name: str | None = None
    ) -> Callable[P, tuple[R | None, Callable[[], None]]]:
    """関数実行時に同時にメモリをプロットする

    Parameters
    ----------
    func : Callable[P, R]
        実行したい関数
    file_name : str | None, optional
        ファイルにアウトプットするかどうか,
        アウトプットするときはそのファイル名, by default None

    Returns
    -------
    Callable[P, tuple[R | None, Callable[[], None]]]
        ラッパーされた関数
        この関数の戻り値は, 実行した関数の戻り値とグラフを閉じる関数
    """
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> tuple[R | None, Callable[[], None]]:
        status = Value('i', 0)
        pid = Value('i', 0)
        result_queue: "Queue[R]" = Queue()

        status.value = Status.WAITING_START
        p_plot = Process(target=plotting, args=(status, pid, file_name))
        p_plot.start()

        p_main = Process(target=local_func, args=(func, result_queue, *args,), kwargs=kwargs)
        p_main.start()

        print('Start plotting')
        parent = psutil.Process(os.getpid())
        children = parent.children()
        pid.value = children[-1].pid
        print(f'Process ID: {children[-1].pid}')

        status.value = Status.RUNNING

        p_main.join()
        time.sleep(0.1)
        status.value = Status.STOP_PLOTTING

        result = result_queue.get()

        def close_figure():
            status.value = Status.CLOSE_FIGURE
            p_plot.join()
            print("Success to close")

        return result, close_figure
    return wrapper
