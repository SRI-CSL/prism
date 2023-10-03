#  Copyright (c) 2019-2023 SRI International.

import json
from pathlib import Path

from prism.config.environment import Range
from prism.config.environment.testbed.docker import generate_docker_compose
from prism.config.node import Client, Server, Bebo


class TestbedRange(Range):
    def __init__(self, client_count: int, server_count: int, bebo_count: int):
        self.bebo_count = bebo_count

        nodes = {}
        client_names = [f"prism-client-{i:05}" for i in range(1, client_count+1)]

        for i, name in enumerate(client_names):
            contacts = [contact for contact in client_names if contact != name]
            nodes[name] = Client(name, enclave="testbed", nat=False, testbed_idx=i+1, contacts=contacts)

        for i in range(1, server_count + 1):
            name = f"prism-server-{i:05}"
            nodes[name] = Server(name, enclave="testbed", nat=False, testbed_idx=i)

        for i in range(1, bebo_count + 1):
            name = f"prism-bebo-{i:05}"
            nodes[name] = Bebo(name, enclave="testbed", nat=False, testbed_idx=i)

        super().__init__(nodes)

    @property
    def bebos(self):
        return [node for node in self.nodes.values() if isinstance(node, Bebo)]

    def write_docker_compose(self, output_path: Path):
        compose = generate_docker_compose(self, output_path)
        with (output_path / "docker-compose.json").open("w") as f:
            json.dump(compose, f, indent=4)
