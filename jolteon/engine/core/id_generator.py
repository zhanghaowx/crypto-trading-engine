import threading
from itertools import count


class IdGenerator:
    def __init__(self):
        self._lock = threading.Lock()
        self._counter = count(start=1)

    def next(self):
        with self._lock:
            return next(self._counter)


def id_generator(singleton=IdGenerator()):
    return singleton
