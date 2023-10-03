#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass, field

from prism.config.config import Configuration
from prism.config.node.client import Client


@dataclass(eq=True, unsafe_hash=True)
class LightsailClient(Client):
    wbs: str = field(default="[]")
    contacts_list: str = field(default="[]")
    db_count: int = 1
    pki_root_cert: str = None

    def config(self, config: Configuration) -> dict:
        client_config = super().config(config)
        return {
            "serviceName": self.name,
            "containers": {
                f"container-{self.name}": {
                    "image": f":{self.name}.prism.latest",
                    "command": [
                        "prism", "client"
                    ],
                    "environment": {
                        "PRISM_whiteboards": self.wbs,
                        "PRISM_wbs_redundancy": "1",
                        "PRISM_name": self.name,
                        "PRISM_private_key": f"'{client_config.get('private_key')}'",
                        "PRISM_pki_root_cert": f"{self.pki_root_cert}" if self.pki_root_cert else "",
                        "PRISM_public_params": self.ibe.public_params,
                        # "PRISM_system_secret": self.ibe.ibe_secrets[0],
                        "PRISM_ibe_shards": "1",
                        "PRISM_contacts": self.contacts_list,
                        "PRISM_client_rest_api": "true",
                        "PRISM_debug": "true",
                        "PRISM_dynamic_links": "false",
                        "PRISM_dropbox_count": f"{self.db_count}",
                        "PRISM_dropbox_poll_with_duration": "false",
                        "PRISM_poll_timing_ms": "120000",
                        "PRISM_onion_layers": "3",
                        "PRISM_is_client": "true"
                    },
                    "ports": {
                        "8080": "HTTP"
                    }
                }
            },
            "publicEndpoint": {
                "containerName": f"container-{self.name}",
                "containerPort": 8080
            }
        }
