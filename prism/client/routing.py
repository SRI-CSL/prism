#  Copyright (c) 2019-2023 SRI International.

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from prism.client.server_db import ServerDB, ServerRecord
from prism.common.message import PrismMessage
from prism.common.message_utils import emix_forward


@dataclass
class MessageRoute:
    route: List[ServerRecord]
    target: ServerRecord
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __str__(self):
        return " -> ".join(s.name for s in [*self.route, self.target])

    def wrap(self, message: PrismMessage):
        target = self.target
        for emix in reversed(self.route):
            message = emix_forward(emix, target, message)
            target = emix
        return message

    def is_dead(self, server_db: ServerDB) -> bool:
        return any(not server_db.can_reach(self.head, s) for s in self.tail)

    @property
    def head(self):
        return self.route[0]

    @property
    def tail(self):
        return [*self.route[1:], self.target]


def find_route(
        server_db: ServerDB,
        starts: List[ServerRecord],
        target: ServerRecord,
        layers: int,
        epoch: str,
) -> Optional[MessageRoute]:
    routes = []

    # Filter the list of starting EMIXes to ones that haven't NARKed the target dropbox
    starts = [start for start in starts if server_db.can_reach(start, target)]

    # For each starting point, tack on some valid EMIXes that haven't been NARKed by the starting point
    for start in starts:
        potential_hops = [emix for emix in server_db.valid_emixes
                          if emix != start and emix.epoch == epoch and
                          server_db.can_reach(start, emix)]

        if len(potential_hops) + 1 < layers:
            continue

        routes.append([start, *random.sample(potential_hops, layers - 1)])

    if not routes:
        return None

    return MessageRoute(random.choice(routes), target)

