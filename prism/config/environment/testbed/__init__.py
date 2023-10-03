#  Copyright (c) 2019-2023 SRI International.

import json
import sys
from pathlib import Path

from prism.common.crypto.ibe import BonehFranklin
from prism.config.config import Configuration
from prism.config.error import ConfigError
from prism.config.generate import run
from prism.config.ibe import CachedIBE, GeneratedIBE
from .deployment import TestbedDeployment
from .range import TestbedRange


def generate_config(args) -> TestbedDeployment:
    deploy = TestbedDeployment(
        test_range=TestbedRange(
            client_count=args.client_count,
            server_count=args.server_count,
            bebo_count=args.bebo_count
        ),
        output_path=Path(args.output_path)
    )

    try:
        deploy.output_path.mkdir(parents=True, exist_ok=True)

        config = Configuration.load_args(args)

        # Apply testbed-specific config settings
        config.topology = "TESTBED"
        config.bootstrapping = False
        config.prism_common["log_dir"] = "/log/prism"
        config.prism_common["ls_routing"] = False
        config.client_common["client_rest_api"] = True

        config.freeze()

        if args.cached_ibe or not BonehFranklin.available():
            cache_file = Path(__file__).parent / f"ibe-cache.json-{config.ibe_shards}"
            ibe_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            ibe_cache_count = len(ibe_cache["private_keys"])

            if args.client_count > ibe_cache_count:
                print(
                    f"Requested client count ({args.client_count}) "
                    f"greater than size of IBE cache ({ibe_cache_count}), and bfibe not available.",
                    file=sys.stderr
                )
                sys.exit(1)
            ibe = CachedIBE(config.ibe_shards, ibe_cache)
        else:
            ibe = GeneratedIBE(config.ibe_shards, config.ibe_dir, config.ibe_level)

        run(deploy, ibe, config)
        return deploy
    except ConfigError as e:
        print(f"Config generation failed: {e}")
        sys.exit(1)
