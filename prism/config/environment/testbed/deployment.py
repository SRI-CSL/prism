#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path
import shutil

from prism.config.config import Configuration
from prism.config.environment.deployment import Deployment
from prism.config.environment.pki_files import generate_pki, create_server_file
from prism.config.environment.testbed.range import TestbedRange
from prism.config.node import Server
from prism.config.topology.graph import draw_graph, can_draw


class TestbedDeployment(Deployment):
    def __init__(self, test_range: TestbedRange, output_path: Path):
        self.output_path = output_path
        self.range: TestbedRange = test_range

    def save(self, config: Configuration):
        keys_path = self.output_path / "config" / "keys"
        shutil.rmtree(keys_path, ignore_errors=True)
        root_pair, epoch_prefixes = generate_pki(config)

        self.write_config(config.prism_common, "prism")
        self.write_config(config.server_common, "server")
        self.write_config(config.client_common, "client")

        if len(epoch_prefixes):
            keys_path.mkdir()
        for node in self.range.nodes.values():
            if node.config(config):
                self.write_config(node.config(config), node.name)
                if isinstance(node, Server):
                    for epoch_prefix in epoch_prefixes:
                        create_server_file(root_pair, keys_path, f"{epoch_prefix}_{node.name}")

        config.write(self.output_path / "input")
        self.range.write_docker_compose(self.output_path)

        if can_draw(self.range):
            draw_graph(self.range.graph, self.output_path / "graph.ps")

    def mkdirs(self):
        super().mkdirs()
        for node in self.range.nodes.values():
            (self.output_path / "logs" / node.name).mkdir(parents=True, exist_ok=True)
