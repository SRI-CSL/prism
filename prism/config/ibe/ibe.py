#  Copyright (c) 2019-2023 SRI International.

import json
from pathlib import Path
from typing import List, Dict

MIN_SECURE_LEVEL = 3


class IBE:
    registrar_name: str = "prism_client_registration"
    public_params: str
    public_param_shards: List[str]
    ibe_secrets: List[str]
    shards: int

    def node_config(self, name) -> dict:
        return {
            "name": name,
            "private_key": self.private_key(name),
        }

    def private_key(self, name: str) -> str:
        pass

    def cleanup(self):
        pass

    def dump(self, out_path: Path):
        if out_path is not None:
            with open(out_path, "w") as fp:
                json.dump({
                    "public_params": self.public_params,
                    "public_param_shards": self.public_param_shards,
                    "ibe_secrets": self.ibe_secrets,
                    "shards": self.shards
                }, fp, indent=2)


    @classmethod
    def load(cls, in_path: Path):
        # this initializes the cached IBE without any private keys,
        # which will be generated at runtime in scaled-up k8s deployments
        if in_path:
            with open(in_path) as fp:
                ibe_dict = json.load(fp)
            ibe = IBE()
            ibe.shards = ibe_dict["shards"]
            ibe.public_params = ibe_dict["public_params"]
            ibe.ibe_secrets = ibe_dict["ibe_secrets"]
            ibe.public_param_shards = ibe_dict["public_param_shards"]
            assert len(ibe.ibe_secrets) == ibe.shards
            return ibe
