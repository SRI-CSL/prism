#  Copyright (c) 2019-2023 SRI International.
import subprocess
from pathlib import Path
from typing import List

from prism.testbed.params import TestParams


class DockerBackend:
    def __init__(self, params: TestParams, dockerfile: Path):
        self.params = params
        self.project = params.project
        self.compose = dockerfile

    def __enter__(self):
        print(f"Starting docker-compose from compose file {self.compose}.")

        result = subprocess.run(self.command('up', '-d'))
        result.check_returncode()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.params.pause_before_exit:
            input("Preparing to clean up testbed. Press ENTER to continue.")
        subprocess.run(self.command('down'))

    def command(self, *args) -> List[str]:
        """Creates a docker-compose command with given arguments."""
        cmd = ['docker-compose',
               '-p', self.project,
               '-f', self.compose]
        cmd.extend(args)
        return cmd