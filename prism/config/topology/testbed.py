#  Copyright (c) 2019-2023 SRI International.

import random
from itertools import groupby
from typing import List, Optional

from prism.config.environment.link import Link
from prism.common.transport.enums import ConnectionType
from prism.config.environment.testbed.range import TestbedRange
from prism.config.node import Server


def testbed_topology(test_range: TestbedRange) -> List[Link]:
    bebo_net = Link(members=test_range.bebos, connection_type=ConnectionType.DIRECT)

    bebos_per_node = min(2, len(test_range.bebos))

    client_bebo_links = [
        Link(
            members=[client, *random.sample(test_range.bebos, k=bebos_per_node)],
            connection_type=ConnectionType.DIRECT)
        for client in test_range.clients
    ]

    server_bebo_links = [
        Link(
            members=[server, *random.sample(test_range.bebos, k=bebos_per_node)],
            connection_type=ConnectionType.DIRECT)
        for server in test_range.servers
        if not server.tags.get("mpc_party_id")
    ]

    def committee(server: Server) -> Optional[int]:
        return server.tags.get("mpc_committee", -1)

    committee_links = [
        Link(members=members, connection_type=ConnectionType.DIRECT)
        for committee_num, members in groupby(sorted(test_range.servers, key=committee), key=committee)
        if committee_num >= 0
    ]

    return [bebo_net, *client_bebo_links, *server_bebo_links, *committee_links]
