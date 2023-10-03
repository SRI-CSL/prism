#  Copyright (c) 2019-2023 SRI International.

import re
from typing import Dict, Optional

from prism.monitor.reader import LogLine


class Parser:
    """Encapsulates a regular expression that returns matches as a dictionary of named values."""

    def __init__(self, pattern: str):
        self.pattern = re.compile(pattern)

    def match(self, line: LogLine) -> Optional[Dict[str, str]]:
        m = self.pattern.search(line.line)

        if m:
            d = m.groupdict()
            if len(d) == 0:
                # Always include at least one value so that returned
                # dicts are truthy, even if otherwise empty.
                d["_ok"] = "True"
            return d
