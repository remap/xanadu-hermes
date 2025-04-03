import multiprocessing
import threading

from .lazy import LazyLoadProxy


__all__ = ['process_pool']

_process_pool = None
_global_lock = threading.Lock()

def get_process_pool(size=5):
    global _process_pool
    with _global_lock:
        if _process_pool is None:
            _process_pool = multiprocessing.Pool(processes=size)
    return _process_pool


process_pool = LazyLoadProxy(get_process_pool)
