#  Copyright (c) 2019-2023 SRI International.
from datetime import datetime, timedelta, timezone
from typing import Dict, Callable

from .parser import Parser
from prism.monitor.reader import LogLine

WARNING_PATTERN = Parser(r"WARNING")


class Node:
    """Parent class for any kind of node that might be running inside the PRISM network."""

    def __init__(self, name: str, epoch: str):
        self.name = name
        self.epoch = epoch
        self.first_activity = datetime.max.replace(tzinfo=timezone.utc)
        self.last_activity = datetime.min.replace(tzinfo=timezone.utc)
        self.monitor_interval = 10
        self.errors = []
        self.warnings = []

    def parse_text_line(
        self, parsers: Dict[str, Parser], func: Callable[[str, Dict[str, str]], None], line: LogLine
    ) -> bool:
        """Runs a text line through a battery of parsers, calling a function with the label and parse results of the
        first matching parser."""
        for label, parser in parsers.items():
            match = parser.match(line)

            if match:
                func(label, match)
                return True

        return False

    def alive(self, now: datetime) -> bool:
        return (now - self.last_activity) < timedelta(seconds=self.monitor_interval * 3)

    def parse(self, line: LogLine) -> bool:
        """Parses a log line. Returns whether or not the line was successfully handled,
        so that subclasses calling up the chain can ignore lines that the superclass handles."""

        if line.file_type == "error":
            if WARNING_PATTERN.match(line):
                self.warnings.append(line.line)
            else:
                self.errors.append(line.line)
            return True

        return False
