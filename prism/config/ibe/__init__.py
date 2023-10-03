#  Copyright (c) 2019-2023 SRI International.

import json
from pathlib import Path
from typing import Optional

from prism.config.error import ConfigError
from prism.config.ibe.cached import CachedIBE
from prism.config.ibe.generated import GeneratedIBE
from prism.config.ibe.ibe import IBE


def create_ibe(ibe_cache: Optional[str], ibe_shards: int, ibe_dir: Optional[str], ibe_level: Optional[int]) -> IBE:
    if ibe_cache:
        cache_path = Path(f"{ibe_cache}-{ibe_shards}")
        if not cache_path.exists():
            raise ConfigError(f"IBE cache at path {cache_path} not found. Try using 1 or 3 IBE shards.")
        cache = json.loads(cache_path.read_text())
        return CachedIBE(ibe_shards, cache)
    else:
        return GeneratedIBE(ibe_shards, ibe_dir, ibe_level)


def save_node_config(ibe_path: Path, name: str, output_path: Path) -> str:
    ibe = CachedIBE.load_from_IBE(ibe_path)
    config = ibe.node_config(name)
    with open(output_path, "w") as fp:
        json.dump(fp, config, indent=2)
    return config["private_key"]
