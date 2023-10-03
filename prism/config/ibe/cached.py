#  Copyright (c) 2019-2023 SRI International.

import argparse
import json
from pathlib import Path
import sys
from typing import List

from prism.config.error import ConfigError
from prism.config.ibe.generated import GeneratedIBE
from prism.config.ibe.ibe import IBE


class CachedIBE(IBE):
    def __init__(self, shards: int, cache: dict):
        self.shards = shards
        self.public_params = cache["public_params"]
        self.private_key_cache = cache["private_keys"]
        self.ibe_secrets = cache["ibe_secrets"]
        self.public_param_shards = cache["public_param_shards"]
        assert len(self.ibe_secrets) == shards

    def private_key(self, name: str) -> str:
        if name in self.private_key_cache:
            return self.private_key_cache[name]
        else:
            raise ConfigError(f"Name {name} not available in IBE cache.")

    def cleanup(self):
        pass

    @staticmethod
    def generate_cache(names: List[str], shards: int, **kwargs) -> dict:
        ibe = GeneratedIBE(shards=shards, **kwargs)
        cache = {
            "public_params": ibe.public_params,
            "public_param_shards": ibe.public_param_shards,
            "ibe_secrets": ibe.ibe_secrets,
            "private_keys": {name: ibe.private_key(name) for name in names}
        }
        ibe.cleanup()
        return cache


def main():
    parser = argparse.ArgumentParser(
        "prism-ibe-cache",
        description="Generate a cached IBE system with preset identities."
    )

    parser.add_argument("--template", "-t", dest="templates", help="Template(s) to use for names.", action="append")
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=1000,
        help="Quantity of names to make identities for with each template."
    )
    parser.add_argument("--shards", "-s", type=int, default=1, help="The number of shards of the secret key to make.")
    parser.add_argument("--out", "-o", type=argparse.FileType("w", encoding="utf-8"))
    parser.add_argument("--first", "-f", type=int, default=1,
                        help="first client index to use (default = 1)")

    args = parser.parse_args()

    templates = args.templates or ["prism-client-%05d"]
    names = [template % i for template in templates for i in range(args.first, args.count+args.first)]
    names.append(CachedIBE.registrar_name)
    for i in range(1, args.shards + 1):
        names.append(f"{CachedIBE.registrar_name}-{i}")
    cache = CachedIBE.generate_cache(names, shards=args.shards)

    if args.out:
        json.dump(cache, args.out, indent=2)
    else:
        json.dump(cache, sys.stdout, indent=2)
