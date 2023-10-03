#  Copyright (c) 2019-2023 SRI International.

import json
from typing import Dict


class LogLine:
    """Holds metadata about a line from a log file. If the log file is natively JSON, parses it."""

    def __init__(self, line: str, tags: Dict[str, str]):
        self.file_type = tags["file_type"]
        self.node_type = tags["node_type"]
        self.node_name = tags["node"]
        self.file_name = tags["file_name"]

        if tags["format"] == "json":
            try:
                self.values = json.loads(line)
            except json.decoder.JSONDecodeError:
                self.values = {}
            self.line = None
        else:
            self.line = line
            self.values = None
