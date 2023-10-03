#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import trio

from prism.server.CS2.roles.lockfree.peer import Peer
from prism.common.config import configuration
from prism.common.message import Share, PreproductInfo


@dataclass
class Triple:
    """
    Shares of a Beaver triple, comprised of random numbers a, b, and c=a*b.
    Used for degree reduction in MPC multiplication.
    """

    a: Share
    b: Share
    c: Share

    def __repr__(self):
        return f"T({self.a}, {self.b}, {self.c})"

    def json(self) -> dict:
        return {
            "a": self.a.json(),
            "b": self.b.json(),
            "c": self.c.json(),
        }


@dataclass
class PreproductChunk:
    """
    A chunk of preproducts to be used in a single MPC operation.
    """

    triples: List[Triple]
    random_numbers: List[Share]

    def __repr__(self):
        return f"Preproducts({self.triples}, {self.random_numbers})"

    def json(self) -> dict:
        return {
            "triples": [t.json() for t in self.triples],
            "random_numbers": [r.json() for r in self.random_numbers],
        }

    @property
    def size(self) -> int:
        return len(self.triples)


@dataclass
class PreproductBatch:
    """
    A batch of MPC preproducts from which chunks can be claimed to use in operations by the batch's owner.
    Exists in parallel on all participating peers.
    """

    batch_id: bytes
    peers: Set[str]
    owned: bool

    triples: List[Optional[Triple]]
    random_numbers: List[Optional[Share]]

    next: int = field(default=0)

    def __repr__(self) -> str:
        return f"Batch({self.batch_id.hex()[:6]}, {self.peers}, {self.remaining}/{len(self.random_numbers)})"

    def json(self) -> dict:
        return {
            "batch_id": self.batch_id.hex(),
            "peers": list(self.peers),
            "owned": self.owned,
            "triples": [t.json() if t else None for t in self.triples],
            "random_numbers": [r.json() if r else None for r in self.random_numbers]
        }

    @property
    def size(self) -> int:
        return len(self.triples)

    def claim_chunk(self, size: int) -> Optional[Tuple[bytes, int, int]]:
        """
        Only for use by the owner of the batch.

        Return the next size unused preproducts from this batch, or None if there aren't enough preproducts remaining.
        """
        assert self.owned

        if size > self.remaining:
            return None

        chunk_info = (self.batch_id, self.next, size)

        self.next += size

        return chunk_info

    def get_chunk(self, start: int, size: int) -> PreproductChunk:
        """
        Return the specified chunk of preproducts from this batch, and nulls them out to prevent double-fetching.
        """
        chunk = PreproductChunk(
            triples=self.triples[start : start + size],
            random_numbers=self.random_numbers[start : start + size],
        )

        assert all(chunk.triples)
        assert all(chunk.random_numbers)

        for i in range(start, start + size):
            self.triples[i] = None
            self.random_numbers[i] = None

        return chunk

    def serves(self, peers: List[Peer], exact: bool = False) -> bool:
        """Return true if all peers in the List are represented in this batch."""
        names = set(peer.name for peer in peers)

        if any(self.batch_id not in peer.preproduct_batches for peer in peers):
            return False

        if exact:
            return names == self.peers
        else:
            return self.peers.issuperset(names)

    @property
    def remaining(self) -> int:
        return max(0, self.size - self.next)


class PreproductStore:
    batches: Dict[bytes, PreproductBatch]

    def __init__(self, logger, mpc_logger):
        self.batches = {}
        self._logger = logger
        self._mpc_logger = mpc_logger

    async def claim_chunk(self, size: int, peers: List[Peer]) -> PreproductInfo:
        """
        Return a chunk of preproducts from a batch that includes the requested peers.
        If there a smaller number than size available, it will return what is available.
        If there are none remaining, it will wait until some preproducts are available.
        """
        i = 0
        while True:
            if self.total_remaining(peers) == 0:
                # Only complain every 30th sleep
                if not i:
                    self._logger.debug("Awaiting preproduct availability.")

                i = (i + 1) % 300
                await trio.sleep(0.1)
                continue

            my_batches = sorted(
                [
                    batch
                    for batch in self.batches.values()
                    if batch.owned and batch.serves(peers) and batch.remaining >= 0
                ],
                key=lambda b: b.remaining,
                reverse=True,
            )

            batches = []
            starts = []
            sizes = []
            to_claim = size
            for batch in my_batches:
                batch_id, start, chunk_size = batch.claim_chunk(min(batch.remaining, to_claim))
                batches.append(batch_id)
                starts.append(start)
                sizes.append(chunk_size)

                to_claim -= chunk_size

                if to_claim <= 0:
                    break

            return PreproductInfo(batches, starts, sizes)

    def get_chunk(self, info: PreproductInfo) -> Optional[PreproductChunk]:
        triples = []
        random_numbers = []
        for batch_id, start, size in zip(info.batches, info.starts, info.sizes):
            if batch_id not in self.batches:
                return None
            chunk = self.batches[batch_id].get_chunk(start, size)
            triples.extend(chunk.triples)
            random_numbers.extend(chunk.random_numbers)

        return PreproductChunk(triples, random_numbers)

    def total_remaining(self, peers: List[Peer], exact: bool = False) -> int:
        def valid_batch(batch: PreproductBatch) -> bool:
            return (
                batch.owned
                and batch.serves(peers, exact=exact)
                and all(batch.batch_id in peer.preproduct_batches for peer in peers)
            )

        return sum(batch.remaining for batch in self.batches.values() if valid_batch(batch))

    def add_batch(self, batch: PreproductBatch):
        self.batches[batch.batch_id] = batch
        if configuration.debug_extra:
            self._mpc_logger.debug("Added batch", batch=batch.json())
