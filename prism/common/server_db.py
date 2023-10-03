#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from prism.common.crypto.halfkey.keyexchange import PublicKey
from prism.common.message import PrismMessage, TypeEnum
from prism.common.pseudonym import Pseudonym
from prism.common.state import StateStore


@dataclass
class ServerRecord:
    pseudonym: bytes
    ark: PrismMessage
    expiration: datetime
    last_broadcast: datetime

    def __init__(self, ark: PrismMessage):
        assert ark.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY
        self.pseudonym = ark.pseudonym
        self.ark = ark
        self.expiration = datetime.utcfromtimestamp(ark.expiration)
        self.last_broadcast = datetime.utcfromtimestamp(0)

    def __repr__(self):
        return f"ServerRecord({self.name} ({self.role}), " + \
               f"expiration={self.expiration}" + \
               (f", last_broadcast={self.last_broadcast})" if self.last_broadcast > datetime.min else ")")

    def to_json(self) -> dict:
        return {
            "ark": self.ark.to_b64(),
            "last_broadcast": self.last_broadcast.timestamp(),
        }

    @classmethod
    def from_json(cls, j: dict) -> ServerRecord:
        ark = PrismMessage.from_b64(j["ark"])
        rec = ServerRecord(ark)
        rec.last_broadcast = datetime.utcfromtimestamp(j["last_broadcast"])
        return rec

    @property
    def name(self) -> str:
        return self.ark.name

    @property
    def epoch(self) -> str:
        return self.ark.epoch

    @property
    def role(self) -> str:
        return self.ark.role

    def valid(self) -> bool:
        return self.expiration > datetime.utcnow()

    def public_key(self, party_id: Optional[int] = None) -> PublicKey:
        if not party_id:
            return self.ark.half_key.to_key()
        else:
            return self.ark.worker_keys[party_id].to_key()

    def update(self, ark: PrismMessage):
        ark_expires = datetime.utcfromtimestamp(ark.expiration)
        if ark_expires > self.expiration:
            self.ark = ark
            self.expiration = ark_expires


class ServerDB:
    servers: Dict[bytes, ServerRecord]

    def __init__(self, state_store: StateStore, epoch: str):
        self.state_store = state_store
        self.current_epoch = epoch
        self.servers = {}
        self.logger = structlog.get_logger(__name__ + ' > ' + self.__class__.__name__)

        saved_state = self.state_store.load_state("server_db")
        if saved_state:
            self.logger.debug("Loading saved ServerDB state")
            self.load(saved_state)

    def __str__(self) -> str:
        return f"ServerDB({len(self.valid_servers)} valid, {len(self.expired_servers)} expired)"

    @property
    def valid_servers(self) -> List[ServerRecord]:
        return [rec for rec in self.servers.values() if rec.valid()]

    @property
    def valid_emixes(self) -> List[ServerRecord]:
        return [rec for rec in self.valid_servers if rec.role == "EMIX"]

    @property
    def expired_servers(self) -> List[ServerRecord]:
        return [rec for rec in self.servers.values() if not rec.valid()]

    def record(self, ark: PrismMessage):
        assert ark.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY

        if ark.pseudonym not in self.servers:
            rec = ServerRecord(ark)
            self.servers[rec.pseudonym] = rec
        else:
            rec = self.servers[ark.pseudonym]
            rec.update(ark)

        self.save()
        return rec

    def dropboxes_for_recipient(
            self,
            pseudonym: Pseudonym,
            dropbox_count: int,
            dropboxes_per_client: int,
            epoch: str,
    ) -> List[ServerRecord]:
        indices = pseudonym.dropbox_indices(dropbox_count, dropboxes_per_client)
        return [rec for rec in self.valid_servers
                if "DROPBOX" in rec.ark.role and
                rec.ark.dropbox_index in indices and
                rec.epoch == epoch]

    def to_json(self) -> dict:
        return {
            "servers": [rec.to_json() for pseudo, rec in self.servers.items()]
        }

    def save(self):
        self.state_store.save_state("server_db", self.to_json())

    def load(self, state: dict):
        if "servers" in state:
            recs = [ServerRecord.from_json(rec_json) for rec_json in state["servers"]]
            self.servers = {rec.pseudonym: rec for rec in recs}
