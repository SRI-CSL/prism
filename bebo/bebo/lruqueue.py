#  Copyright (c) 2019-2023 SRI International.

import collections
import trio

DEFAULT_MAX_COUNT = 10000
DEFAULT_MAX_SIZE = 10000000

def _default_sizer(content):
    try:
        return content.size()
    except AttributeError:
        return len(content)

class LRUQueue:
    def __init__(self, max_count=DEFAULT_MAX_COUNT, max_size=DEFAULT_MAX_SIZE,
                 sizer=None):
        if sizer is None:
            sizer = _default_sizer
        self.lock = trio.Lock()
        self.condition = trio.Condition(self.lock)
        self.deque = collections.deque([], max_count)
        self.max_count = max_count
        self.max_size = max_size
        self.sizer = sizer
        self.size = 0

    def _unlocked_read(self):
        # Internal use only!
        content = self.deque.popleft()
        size = self.sizer(content)
        assert size >= 0
        self.size -= size
        # just in case
        if self.size < 0:
            self.size = 0
        return content

    async def write(self, content):
        async with self.condition:
            size = self.sizer(content)
            assert size >= 0
            if size > DEFAULT_MAX_SIZE:
                raise ValueError('content too large')
            self.size += size
            while self.size > self.max_size:
                self._unlocked_read()
            self.deque.append(content)
            self.condition.notify_all()

    async def read(self):
        async with self.condition:
            while True:
                try:
                    return self._unlocked_read()
                except IndexError:
                    await self.condition.wait()

    async def unread(self, message):
        async with self.condition:
            size = self.sizer(content)
            assert size >= 0
            if size + self.size <= self.max_size and \
               len(self.deque) < self.max_size:
                self.deque.appendleft(message)
