#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Set

from prism.common.message import HalfKeyMap


@dataclass
class Peer:
    party_id: int
    name: str
    pseudonym: bytes = field(default=None)
    ready: bool = field(default=False)
    local: bool = field(default=False)
    last_hello_ack: datetime = field(default=None)
    last_modulus_ack: datetime = field(default=None)
    last_ready_ack: datetime = field(default=None)
    preproduct_batches: Set[bytes] = field(default_factory=set)
    half_key: Optional[HalfKeyMap] = field(default=None)

    def __repr__(self) -> str:
        if self.pseudonym:
            ps = f", {self.pseudonym.hex()[:6]}"
        else:
            ps = ""
        return f"Peer({self.party_id}, {self.name}{ps})"

    @property
    def ark_key(self) -> Optional[HalfKeyMap]:
        if self.ready:
            return self.half_key

    def to_dict(self) -> dict:
        return {
            "party_id": self.party_id,
            "name": self.name,
            "ready": self.ready,
        }


@dataclass
class DropboxPeer(Peer):
    stored_fragments: Set[bytes] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "stored_fragments": len(self.stored_fragments),
        }

    def __repr__(self) -> str:
        return f"DBPeer({self.party_id}, {self.name})"
