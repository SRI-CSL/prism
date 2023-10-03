#  Copyright (c) 2019-2023 SRI International.

# version information:
from pathlib import Path

version_path = Path("/opt/prism/VERSION")
version_info = {}

if version_path.exists():
    with version_path.open() as version_file:
        for line in version_file:
            key, value = line.rstrip().partition("=")[::2]
            version_info[key.strip()] = value
