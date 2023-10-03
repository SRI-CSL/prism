#  Copyright (c) 2019-2023 SRI International.

import time
import uuid

from typing import Optional, List, Tuple

from bebo.protocol import RelayMessage

DEFAULT_MAX_COUNT = 100000
DEFAULT_MAX_SIZE = 100000000
DEFAULT_MAX_AGE = 300  # XXXRTH artificially low for testing

class Storage:
    def __init__(self, max_count: int=DEFAULT_MAX_COUNT,
                 max_size: int=DEFAULT_MAX_SIZE,
                 max_age: int=DEFAULT_MAX_AGE):
        assert max_count > 0
        assert max_size > 0
        self.max_count = max_count
        self.max_size = max_size
        self.max_age = max_age
        self.size = 0
        self.flush()

    def flush(self):
        self.uuid = uuid.uuid4()
        self.least_sequence_number = 0
        self.next_sequence_number = 1
        self.by_key = {}
        self.by_sequence_number = {}
        self.seen_by_id = {}
        self.size = 0

    def add(self, message: RelayMessage, now: Optional[int]=None) \
        -> Tuple[Optional[RelayMessage], int]:
        key = message.key()
        existing = self.get_by_key(key)
        if existing:
            return (existing, existing.sequence_number)
        self.by_key[key] = message
        seqno = self.next_sequence_number
        self.next_sequence_number += 1
        if not self.least_sequence_number:
            # This is the first message added since we had a "no messages"
            # state.
            self.least_sequence_number = seqno
        message.sequence_number = seqno
        if now is None:
            now = time.time()
        message.timestamp = now
        self.by_sequence_number[seqno] = message
        self.size += message.size()
        self.purge(now)
        return (None, seqno)

    def get_by_sequence_number(self, sequence_number: int) -> \
            Optional[RelayMessage]:
        return self.by_sequence_number.get(sequence_number)

    def get_by_key(self, key: str) -> Optional[RelayMessage]:
        return self.by_key.get(key)

    def get_message(self, message: RelayMessage) -> Optional[RelayMessage]:
        return self.by_key.get(message.key())

    def contains(self, message: RelayMessage) -> bool:
        return self.get_by_key(message.key()) is not None

    def messages_for_id(self, listener_id: str) -> List[RelayMessage]:
        seen = self.seen_by_id.get(listener_id)
        if not seen:
            seen = set()
            self.seen_by_id[listener_id] = seen
        keys = [key for key in self.by_key if key not in seen]
        seen.update(keys)
        return [self.by_key[key] for key in keys]

    def next_to_purge(self, now):
        if self.least_sequence_number > 0:
            message = self.by_sequence_number[self.least_sequence_number]
            age = max(now - message.timestamp, 0)
            if len(self.by_sequence_number) > self.max_count or \
               self.size > self.max_size or \
               age > self.max_age:
                return message
        return None

    def purge(self, now=None):
        if now is None:
            now = time.time()
        while True:
            message = self.next_to_purge(now)
            if not message:
                break
            del self.by_sequence_number[message.sequence_number]
            self.least_sequence_number = message.sequence_number + 1
            assert self.least_sequence_number <= self.next_sequence_number
            if self.least_sequence_number == self.next_sequence_number:
                # restore the "empty" state
                self.least_sequence_number = 0
            key = message.key()
            del self.by_key[key]
            for seen in self.seen_by_id.values():
                seen.discard(key)
            self.size -= message.size()
            if self.size < 0:
                # shouldn't happen, but just in case...
                self.size = 0
        assert self.least_sequence_number < self.next_sequence_number

    def state(self):
        s = {'uuid': self.uuid}
        if self.least_sequence_number > 0:
            s['least'] = self.least_sequence_number
            s['greatest'] = self.next_sequence_number - 1
        return s

    def get_range(self, first, count):
        if first == 0:
            first = self.least_sequence_number
        end = min(first + count, self.next_sequence_number)
        messages = []
        for i in range(first, end):
            message = self.get_by_sequence_number(i)
            if message:
                messages.append((i, message))
        return messages
