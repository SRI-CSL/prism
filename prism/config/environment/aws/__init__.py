#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path
import structlog
import sys
from typing import List

from prism.config.config import Configuration
from prism.config.error import ConfigError
from prism.config.generate import run
from prism.config.ibe import GeneratedIBE
from .deployment import AWSDeployment
from .range import AWSRange, LocalRange

LOGGER = structlog.getLogger("prism.config.environment.aws")


def generate_aws_config(args, db_count: int, clients: List, pki_root_cert: str = None) -> AWSDeployment:
    LOGGER.info(f"generate AWS config with db_count={db_count} and {len(clients)} clients{' and root cert' if pki_root_cert else ''}")
    deploy = AWSDeployment(
        AWSRange(db_count, clients, pki_root_cert),
        output_path=Path(args.output_path)
    )

    try:
        deploy.output_path.mkdir(parents=True, exist_ok=True)

        config = Configuration.load_args(args)
        # Apply AWS-specific config settings
        config.bootstrapping = False
        # config.prism_client["dynamic_links"] = False

        ibe = GeneratedIBE(config.ibe_shards, config.ibe_dir, config.ibe_level)
        run(deploy, ibe, config)
        return deploy
    except ConfigError as e:
        print(f"AWS Config generation failed: {e}")
        sys.exit(1)


def generate_local_config(args, db_count: int, clients: List, pki_root_cert: str = None) -> AWSDeployment:
    LOGGER.info(f"generate local config with db_count={db_count} and {len(clients)} clients{' and root cert' if pki_root_cert else ''}")
    deploy = AWSDeployment(
        LocalRange(db_count, clients, pki_root_cert),
        output_path=Path(args.output_path)
    )

    try:
        deploy.output_path.mkdir(parents=True, exist_ok=True)

        config = Configuration.load_args(args)
        # Apply AWS-specific config settings
        config.bootstrapping = False
        # config.prism_client["dynamic_links"] = False

        ibe = GeneratedIBE(config.ibe_shards, config.ibe_dir, config.ibe_level)
        run(deploy, ibe, config)
        return deploy
    except ConfigError as e:
        print(f"Local Config generation failed: {e}")
        sys.exit(1)
