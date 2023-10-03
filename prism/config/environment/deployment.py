#  Copyright (c) 2019-2023 SRI International.

import json
import shutil
from pathlib import Path
from typing import List

from prism.config.config import Configuration
from prism.config.environment.range import Range
from prism.config.error import ConfigError
from prism.config.node.server import Dropbox, Emix


class Deployment:
    range: Range
    output_path: Path

    def save(self, config: Configuration):
        """Writes configuration information to files that can be loaded by PRISM nodes."""
        pass

    def check(self, config: Configuration) -> List[ConfigError]:
        """Checks for errors in configuration and returns a list of mistakes found."""
        errors = []

        def error(explanation: str):
            errors.append(ConfigError(explanation))

        if "threshold" in config.server_common:
            if config.server_common["threshold"] > config.mpc_committee_size:
                error(
                    f"MPC threshold ({config.server_common['threshold']}) "
                    f"greater than MPC committee size ({config.mpc_committee_size})."
                )

        dropboxes = self.range.servers_with_role(Dropbox)
        emixes = self.range.servers_with_role(Emix)

        if len(dropboxes) < 1 and config.strict_dropbox_count:
            error("No dropboxes assigned.")
        if len(emixes) < 1:
            error("No Emixes assigned.")

        if config.prism_common["dropboxes_per_client"] > len(dropboxes) and config.strict_dropbox_count:
            error(
                f"prism.dropboxes_per_client ({config.prism_common['dropboxes_per_client']}) "
                f"is greater than actual dropbox count ({len(dropboxes)})."
            )

        return errors

    def mkdirs(self):
        """Makes any output directories necessary for the deployment."""
        self.output_path.mkdir(parents=True, exist_ok=True)

    def write_json(self, path: Path, d: dict):
        with path.open("w") as f:
            json.dump(d, f, indent=2)

    def write_config(self, cfg, name, config_type="config"):
        parent_dir = self.output_path / config_type
        parent_dir.mkdir(exist_ok=True, parents=True)
        self.write_json(parent_dir / f"{name}.json", cfg)
