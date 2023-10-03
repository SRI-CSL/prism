#  Copyright (c) 2019-2023 SRI International.

from datetime import datetime, timedelta
from time import time
from typing import List, Optional

from prism.common.message import PrismMessage, TypeEnum
from prism.common.server_db import ServerDB
from prism.server.server_data import ServerData


class ArkStore(ServerDB):
    def record(self, ark: PrismMessage, rebroadcast=False):
        rec = super().record(ark)
        if not rec.valid():
            self.remove(rec.pseudonym)

        if rebroadcast:
            rec.last_broadcast = datetime.utcfromtimestamp(0)

    def promote(self, pseudonym: bytes):
        """If record for this pseudonym exists, promote it in queue by setting last_broadcast to datetime.min + 1"""
        rec = self.servers.get(pseudonym, None)
        if rec is not None:
            rec.last_broadcast = datetime.utcfromtimestamp(0) + timedelta(seconds=1)

    def remove(self, pseudonym: bytes):
        """Remove entry for given pseudonym (if it exists)"""
        self.servers.pop(pseudonym, None)
        self.save()

    def broadcast_message(self, server_data: ServerData, mtu: int) -> Optional[PrismMessage]:
        """Finds the batch_size least recently broadcast ARKs, updates their broadcast time, and returns an ARKS message
        to be sent out."""
        non_dummy_servers = [server for server in self.valid_servers if server.role != "DUMMY"]
        records_by_last_broadcast = sorted(non_dummy_servers, key=lambda s: s.last_broadcast)
        batch = []
        message = None
        new_size = 0

        for batch_size in range(1, len(records_by_last_broadcast) + 1):
            new_batch = records_by_last_broadcast[:batch_size]
            new_message = PrismMessage(
                msg_type=TypeEnum.ARKS,
                pseudonym=server_data.pseudonym,
                epoch=server_data.epoch,
                micro_timestamp=int(time() * 1e6),
                submessages=[rec.ark for rec in new_batch],
            )
            new_size = len(new_message.encode())

            if new_size > mtu:
                break
            else:
                batch = new_batch
                message = new_message

        if new_size and message is None:
            self.logger.warning(f"Single ARK produces message size ({new_size}) greater than MTU {mtu}.")

        for rec in batch:
            rec.last_broadcast = datetime.utcnow()

        return message
