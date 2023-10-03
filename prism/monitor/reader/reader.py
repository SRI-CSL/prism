#  Copyright (c) 2019-2023 SRI International.
from dataclasses import dataclass, field

import trio


@dataclass
class ReaderStats:
    lines_read: int = field(default=0)


class Reader:
    """Common superclass/interface for readers."""

    def __init__(self):
        self.stats = ReaderStats()

    async def run(self, line_in: trio.MemorySendChannel):
        pass
