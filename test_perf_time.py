import timeit

setup = """
import time
def get_time():
    return time.time()
"""

setup_monotonic = """
import time
def get_time():
    return time.monotonic()
"""

setup_perf = """
import time
def get_time():
    return time.perf_counter()
"""

try:
    time_time = timeit.timeit("get_time()", setup=setup, number=10000000)
    monotonic_time = timeit.timeit("get_time()", setup=setup_monotonic, number=10000000)
    perf_time = timeit.timeit("get_time()", setup=setup_perf, number=10000000)

    print(f"time.time(): {time_time:.4f}s")
    print(f"time.monotonic(): {monotonic_time:.4f}s")
    print(f"time.perf_counter(): {perf_time:.4f}s")
    print(f"Improvement: {(time_time - perf_time) / time_time * 100:.2f}%")
except Exception as e:
    import traceback
    traceback.print_exc()
