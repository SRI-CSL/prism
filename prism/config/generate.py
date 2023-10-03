#  Copyright (c) 2019-2023 SRI International.

import random

from prism.config.config import Configuration
from prism.config.environment import Deployment
from prism.config.ibe.ibe import IBE


def run(deployment: Deployment, ibe: IBE, config: Configuration):
    if config.random_seed:
        random.seed(config.random_seed)

    try:
        deployment.mkdirs()
        if config.sortition == "STATIC":
            deployment.range.assign_roles(config, ibe)
        elif config.sortition == "VRF":
            deployment.range.perform_sortition(config, ibe)
        elif config.sortition == "DUMMIES":
            deployment.range.genesis_dummies(config, ibe)
        else:
            print(f"Don't understand config sortition mode={config.sortition} - aborting!")
            return
        deployment.range.configure_roles(config, ibe)
        deployment.range.configure_topology(config)

        errors = deployment.check(config)
        if errors:
            for error in errors:
                print(error)
                print()
            print(f"Found {len(errors)} errors that prevent config generation:")
            return

        deployment.save(config)
    finally:
        if not config.ibe_dir:
            ibe.cleanup()
