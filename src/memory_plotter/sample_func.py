from time import sleep

from memory_plotter.plot_mem import realtime_mem_plot


# @realtime_mem_plot  # この記法では動作しない... なぜ?
def test_func(name, name2, rep=2):
    """お試し関数"""
    print(name)
    for j in range(10):
        k = []
        for _ in range(100):
            k.append([0]*10000*j)
            sleep(0.01)
        del k
        sleep(0.1)
    for _ in range(rep):
        print(name2)
    return 10, 20

if __name__ == '__main__':  # これを書かないと動かない (呼び出しがループするため)
    # 使い方
    # 1. 計測したい関数を持ってきて, 設定する
    f_with_plot = realtime_mem_plot(test_func)
    func_results, closing = f_with_plot('test', 'test2', rep=2)
    print(func_results)

    input("Please press Enter key to close")
    closing()

    print("Finished")
