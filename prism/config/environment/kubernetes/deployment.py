#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path
import shutil
import structlog

from prism.config.config import Configuration
from prism.config.environment.deployment import Deployment
from .k8s_range import KubernetesRange


class KubernetesDeployment(Deployment):
    def __init__(self, k8s_range: KubernetesRange, output_path: Path):
        self.output_path = output_path
        self.range: KubernetesRange = k8s_range

    def save(self, config: Configuration):
        config_path = self.output_path / "config"
        if config_path.exists():
            shutil.rmtree(config_path)
        for node in self.range.nodes.values():
            if node.config(config) and node.client_ish:
                self.write_config(node.config(config), node.name)
                yaml_str = getattr(node, "yaml_str", "")
                if yaml_str:
                    deployment_file = config_path / f"{node.name}-deployment.yaml"
                    with open(deployment_file, 'w') as yfile:
                        yfile.write(yaml_str)
                    structlog.getLogger("prism.config.environment.kubernetes").info(f"Wrote file {deployment_file}")
