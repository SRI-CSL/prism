#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

import hashlib
from datetime import datetime


class Pseudonym:
    def __init__(self, pseudonym: bytes):
        self.pseudonym = pseudonym

    def __str__(self):
        return self.pseudonym.hex()

    @classmethod
    def from_address(cls, address: str, salt: str) -> Pseudonym:
        date_str = datetime.utcnow().date().isoformat()
        salt = salt.replace("{date}", date_str)
        pseudo_string = f"{salt}{address}"
        sha = hashlib.sha256()
        sha.update(pseudo_string.encode("utf-8"))

        return Pseudonym(sha.digest())

    def dropbox_indices(self, dropbox_count: int, dropboxes_per_client: int):
        int_value = int.from_bytes(self.pseudonym, byteorder="big", signed=False)
        base_index = int_value % dropbox_count
        return {(base_index + i) % dropbox_count for i in range(dropboxes_per_client)}
