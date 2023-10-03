#  Copyright (c) 2019-2023 SRI International.

from typing import List

from prism.config.environment import Range
from prism.config.environment.kubernetes.k8s_client import KubernetesClientSet
from prism.config.node import Server


class KubernetesRange(Range):
    def __init__(self, db_count: int, wbs: str):
        nodes = {}

        nodes["prism-client"] = KubernetesClientSet("prism-client",
                                                    enclave="k8s", nat=False,
                                                    wbs=wbs,
                                                    db_count=db_count)

        # add straw men servers so that IBE does not barf:
        for i in range(1, 8):
            name = f"prism-server-{i:05}"
            nodes[name] = Server(name, enclave="k8s", nat=False, testbed_idx=i)

        super().__init__(nodes)
