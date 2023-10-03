#  Copyright (c) 2019-2023 SRI International.

import json
from pathlib import Path
from typing import List

from prism.common.message import PrismMessage
from prism.config.config import Configuration
from prism.config.environment import Range
from prism.config.node import Node
from prism.config.node.server import ClientRegistration, Server, Dummy


class ControlCache:
    arks: List[PrismMessage]
    lsp_cache: str

    def __init__(self, test_range: Range, config: Configuration):
        self.arks = []

        lsps = []
        for server in test_range.servers:
            if server.is_role(ClientRegistration) or server.is_role(Dummy):
                continue

            ark = server.ark(config)
            if ark:
                self.arks.append(ark)

            lsp = server.lsp(config).to_b64()
            lsps.append(lsp)

        self.lsp_cache = json.dumps({"database": lsps})

    def write_for(self, config_dir: Path, node: Node):
        if isinstance(node, Server) and not (node.is_role(ClientRegistration) or node.is_role(Dummy)):
            (config_dir / "lsp.json").write_text(self.lsp_cache)

        server_db = {"servers": [{"ark": ark.to_b64(), "last_broadcast": 0}
                                 for ark in self.arks if ark.name != node.name]}
        ark_cache = json.dumps(server_db)
        (config_dir / "server_db.json").write_text(ark_cache)
