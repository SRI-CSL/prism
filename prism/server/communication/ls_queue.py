#  Copyright (c) 2019-2023 SRI International.
from dataclasses import dataclass
from enum import Enum, auto
import heapq
import structlog
import trio
from typing import List

from prism.common.config import configuration
from prism.common.util import bytes_hex_abbrv


@dataclass(frozen=True)
class QItem:
    neighbor: bytes
    originator: bytes

    def __str__(self):
        return f'<{bytes_hex_abbrv(self.neighbor)},{bytes_hex_abbrv(self.originator)}>'


@dataclass(eq=False, order=False, frozen=True)
class PrioritizedQItem(QItem):
    expiration: float

    def __str__(self):
        return f'{str(super())} expires at {self.expiration:2f}'

    def __eq__(self, other):
        # customized equality to only use superclass
        if not isinstance(other, QItem):
            return False
        return self.neighbor == other.neighbor and self.originator == other.originator

    def __gt__(self, other):
        if not isinstance(other, PrioritizedQItem):
            raise ValueError(f'Cannot compare {self} to {other}')
        return self.expiration > other.expiration


class QType(Enum):
    SEND = auto()
    ACK = auto()
    RETRANS = auto()


class LSQueue:

    def __init__(self, qtype: QType, send_ch: trio.MemorySendChannel):
        self._logger = structlog.getLogger(__name__).bind(type=qtype.name)
        # backing the Q by a list to be able to manipulate items:
        self._q_list: List[QItem] = []
        self._q_type = qtype
        assert send_ch
        self._send_ch = send_ch
        self._q_lock = trio.StrictFIFOLock()

    async def insert_item(self, item: QItem):
        """
        If item is already present in Q, keep it and ignore new one.
        Otherwise, add new item to the end (and sort if priority).
        """
        assert item
        async with self._q_lock:
            try:
                self._q_list.index(item)
            except ValueError:
                # item to be inserted is not present
                self._q_list.append(item)
                if self._q_type == QType.RETRANS:
                    assert isinstance(item, PrioritizedQItem)
                    heapq.heapify(self._q_list)  # sort by expiration
            # self._logger.debug(f'Q has {len(self._q_list)} items')

    async def remove_item_for_neighbor(self, neighbor: bytes):
        """
        Remove all items from Q that match given neighbor.
        """
        async with self._q_lock:
            self._q_list = [qi for qi in self._q_list if qi.neighbor != neighbor]

    async def rate_limited_processing(self):
        while True:
            head = None
            async with self._q_lock:
                # TODO: Linda: do something different for priority queue: peek at expiration of head and set timer?
                if len(self._q_list) > 0:
                    head = self._q_list.pop(0)
            if head:
                # process head item (if there was one)
                assert isinstance(head, QItem)
                await self._send_ch.send((self._q_type, head.neighbor, head.originator))
            await trio.sleep(configuration.ls_q_rate_limit)
