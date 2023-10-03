#  Copyright (c) 2019-2023 SRI International.

from collections import defaultdict
from random import Random
from typing import List

from prism.common.transport.enums import ConnectionType
from prism.config.config import Configuration
from prism.config.environment import Range
from prism.config.environment.link import Link
from prism.config.node.server import ClientRegistration, Emix


def connect_clients_to_emixes(config: Configuration, test_range: Range, rand: Random) -> List[Link]:
    registration_committee = set(test_range.servers_with_role(ClientRegistration))
    clients = set(test_range.clients).union(registration_committee)
    emixes = set(test_range.servers_with_role(Emix))
    emix_clients = defaultdict(list)
    links = []

    for client in clients:
        for emix in rand.sample(emixes, min(config.emixes_per_client, len(emixes))):
            links.append(Link(
                senders=[client],
                receivers=[emix],
                connection_type=ConnectionType.INDIRECT,
                tags=["uplink"]
            ))
            emix_clients[emix].append(client)

    for emix, clients in emix_clients.items():
        links.append(Link(senders=[emix], receivers=clients, connection_type=ConnectionType.INDIRECT, tags=["ark"]))

    return links
