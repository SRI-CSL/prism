#  Copyright (c) 2019-2023 SRI International.

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from queue import Queue, Empty
from typing import List, Optional

from prism.common.config import configuration
from prism.client.routing import MessageRoute
from prism.client.server_db import ServerDB, ServerRecord
from prism.common.cleartext import ClearText


@dataclass
class SendLogEntry:
    message: ClearText
    routes_sent: List[MessageRoute] = field(default_factory=list)

    @property
    def dropboxes_sent(self) -> List[ServerRecord]:
        return [route.target for route in self.routes_sent]

    @property
    def sends_remaining(self) -> int:
        return configuration.dropbox_send_redundancy - len(self.dropboxes_sent)

    @property
    def finished(self) -> bool:
        return self.sends_remaining < 1

    @property
    def last_sent(self) -> Optional[datetime]:
        if self.routes_sent:
            return max(route.timestamp for route in self.routes_sent)
        else:
            return None

    def __str__(self):
        return "MessageLog.Entry(\n" + \
               "\n".join(str(route) for route in self.routes_sent) + \
               "\n"

    def targets(self, candidates: List[ServerRecord]) -> List[ServerRecord]:
        return [candidate for candidate in candidates if candidate not in self.dropboxes_sent]

    def sent(self, route: MessageRoute):
        self.routes_sent.append(route)

    def invalidate_routes(self, server_db: ServerDB):
        self.routes_sent = [route for route in self.routes_sent if not route.is_dead(server_db)]

    @property
    def safe(self) -> bool:
        if not self.finished:
            return False

        interval = datetime.utcnow() - self.last_sent
        return interval.total_seconds() * 1000 > (configuration.poll_timing_ms * 2)


class SendLog:
    def __init__(self, server_db: ServerDB):
        self.server_db = server_db
        self.backlog = Queue()
        self.complete = []

    def add(self, message: ClearText):
        # TODO - check here if there's a deadlock
        self.backlog.put(SendLogEntry(message))

    @contextmanager
    def attempt(self):
        self.cleanup_complete()

        try:
            entry = self.backlog.get_nowait()
        except Empty:
            yield None
            return
        entry.invalidate_routes(self.server_db)

        yield entry

        if entry.finished:
            self.complete.append(entry)
        else:
            self.backlog.put(entry)

    def cleanup_complete(self):
        for entry in self.complete:
            entry.invalidate_routes(self.server_db)
            if not entry.finished:
                self.backlog.put(entry)

        self.complete = [entry for entry in self.complete if entry.finished and not entry.safe]

    def empty(self):
        return self.backlog.empty()

    def __len__(self):
        return self.backlog.qsize()
