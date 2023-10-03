#  Copyright (c) 2019-2023 SRI International.

from typing import List

from prism.config.environment import Range
from prism.config.environment.aws.lightsail_client import LightsailClient
from prism.config.environment.aws.local_client import LocalClient
from prism.config.node import Server


class AWSRange(Range):
    def __init__(self, db_count: int, clients: List, pki_root_cert: str = None):
        nodes = {}

        for client in clients:
            nodes[client["name"]] = LightsailClient(client["name"],
                                                    enclave="aws", nat=False,
                                                    wbs=client["wbs"],
                                                    contacts_list=client["contact_list"],
                                                    db_count=db_count,
                                                    pki_root_cert=pki_root_cert)

        # add straw men servers so that IBE does not barf:
        for i in range(1, 8):
            name = f"prism-server-{i:05}"
            nodes[name] = Server(name, enclave="aws", nat=False, testbed_idx=i)

        super().__init__(nodes)


class LocalRange(Range):
    def __init__(self, db_count: int, clients: List, pki_root_cert: str = None):
        nodes = {}

        for i, client in enumerate(clients, start=1):
            nodes[client["name"]] = LocalClient(client["name"],
                                                enclave="aws", nat=False,
                                                wbs=client["wbs"],
                                                contacts_list=client["contact_list"],
                                                db_count=db_count,
                                                pki_root_cert=pki_root_cert,
                                                ordinal=i)

        # add straw men servers so that IBE does not barf:
        for i in range(1, 8):
            name = f"prism-server-{i:05}"
            nodes[name] = Server(name, enclave="aws", nat=False, testbed_idx=i)

        super().__init__(nodes)
