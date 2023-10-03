#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from jaeger_client import SpanContext

from prism.common.message import Share


@dataclass
class Fragment:
    fragment_id: bytes
    pseudonym_share: Share
    ciphertext: bytes
    store_context: Optional[SpanContext]

    def __repr__(self) -> str:
        trace = self.store_context and hex(self.store_context.trace_id)[2:]
        return f"Fragment({self.fragment_id.hex()[:6]}, tr: {trace})"

    def json(self) -> dict:
        return {
            "id": self.fragment_id.hex(),
            "share": self.pseudonym_share.json(),
            "store_trace": hex(self.store_context.trace_id)[2:]
        }

    @staticmethod
    def dummy() -> Fragment:
        return Fragment(b"", Share(0, -1), b"", None)
