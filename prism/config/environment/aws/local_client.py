#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass, field

from prism.config.config import Configuration
from prism.config.node.client import Client


@dataclass(eq=True, unsafe_hash=True)
class LocalClient(Client):
    wbs: str = field(default="[]")
    contacts_list: str = field(default="[]")
    db_count: int = 1
    pki_root_cert: str = None
    ordinal: int = 1

    def config(self, config: Configuration) -> dict:
        client_config = super().config(config)
        return {
            f"{self.name.lower()}": {
                "command": ["prism", "client"],
                "container_name": f"{self.name.lower()}",
                "image": "race-ta1-docker.cse.sri.com/prism:latest",
                "ports": [f"{7000 + self.ordinal}:8080"],
                "environment": {
                    "PRISM_wbs_redundancy": "1",
                    "PRISM_client_rest_api": "true",
                    "PRISM_debug": "true",
                    "PRISM_dynamic_links": "false",
                    "PRISM_dropbox_count": f"{self.db_count}",
                    "PRISM_dropbox_poll_with_duration": "false",
                    "PRISM_poll_timing_ms": "20000",
                    "PRISM_onion_layers": "3",
                    "PRISM_is_client": "true",
                    "PRISM_pki_root_cert": f"{self.pki_root_cert}" if self.pki_root_cert else "",
                    "PRISM_whiteboards": self.wbs,
                    "PRISM_name": self.name,
                    "PRISM_contacts": self.contacts_list,
                    "PRISM_public_params": self.ibe.public_params,
                    "PRISM_private_key": f"'{client_config.get('private_key')}'",
                }
            }
        }
