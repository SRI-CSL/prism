#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path
from typing import Dict, Any, List

import structlog
import trio


def loaded_and_sorted_dict(configuration) -> Dict[str, Any]:
    keys = set()
    for keys_to_add in [set(d.keys()) for d in list(configuration.loaded_by_loaders.values())]:
        keys.update(keys_to_add)
        return {str(key).lower(): configuration.get(key) for key in sorted(keys)}


class Watchdog:
    def __init__(self, configuration, file_paths: List[Path]):
        self.configuration = configuration
        self.file_paths = file_paths
        self._logger = structlog.getLogger(__name__)

    async def main(self):
        while True:
            stamps = [file_path.stat().st_mtime for file_path in self.file_paths]

            # sleep at least 1 second unless negative, then stop!
            watchdog_sleep = self.configuration.get('watchdog_sleep', default=1.0)
            if watchdog_sleep < 0:
                self._logger.info(f'Watchdog for modified configuration encountered negative sleep: stopping!')
                break
            await trio.sleep(max(watchdog_sleep, 1.0))
            for index, stamp in enumerate(stamps):
                if stamp != self.file_paths[index].stat().st_mtime:
                    self.configuration.load_file(path=str(self.file_paths[index]))
                    self._logger.info(f'Reloaded configuration from file {self.file_paths[index]}',
                                      config=loaded_and_sorted_dict(self.configuration),
                                      path=self.file_paths[index])
