#  Copyright (c) 2019-2023 SRI International.

# file_type informs the dispatcher and handling classes of what information might be present in a log line.
# If format == 'json', then it will automatically be parsed into a dictionary.
from typing import Dict

MONITOR_FILES: Dict[str, Dict[str, str]] = {
    "prism/prism.server.monitor.log": {
        "file_type": "monitor",
        "format": "json",
        "node_type": "server",
    },
    "prism/prism.client.monitor.log": {
        "file_type": "monitor",
        "format": "json",
        "node_type": "client",
    },
}
REPLAY_FILES: Dict[str, Dict[str, str]] = {
    "prism/replay.log": {"file_type": "replay", "format": "json"},
    "prism/receive.log": {"file_type": "replay", "format": "json"},
}


