#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path

REPO_ROOT = next(p for p in Path(__file__).parents
                    if (p / 'VERSION').exists())
VERSION = (REPO_ROOT / 'VERSION').read_text().strip()

TEST_RUN_PATH = REPO_ROOT / "integration-tests" / "runs"
ACTIVE_TEST_FILE = TEST_RUN_PATH / "current.txt"
