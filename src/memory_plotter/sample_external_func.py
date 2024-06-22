from memory_plotter.plot_mem import realtime_mem_plot
from memory_plotter.sample_func import test_func

if __name__ == '__main__':  # これを書かないと動かない (呼び出しがループするため)
    # 使い方
    # 1. 計測したい関数を持ってきて, 設定する
    f_with_plot = realtime_mem_plot(test_func, "mem.csv")
    func_results, closing = f_with_plot('test', 'test2', rep=2)
    print(func_results)

    input("Please press Enter key to close")
    closing()

    print("Finished")
