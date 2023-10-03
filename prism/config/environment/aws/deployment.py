#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path
import shutil
from typing import *

from prism.config.config import Configuration
from prism.config.environment.deployment import Deployment
from .range import AWSRange, LocalRange


class AWSDeployment(Deployment):
    def __init__(self, aws_range: Union[AWSRange, LocalRange], output_path: Path):
        self.output_path = output_path
        self.range: AWSRange = aws_range

    def save(self, config: Configuration):
        shutil.rmtree(self.output_path / "config", ignore_errors=True)
        for node in self.range.nodes.values():
            if node.config(config) and node.client_ish:
                self.write_config(node.config(config), node.name)
