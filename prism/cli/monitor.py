#  Copyright (c) 2019-2023 SRI International.

import time
from pathlib import Path

import trio

from prism.cli.command import CLICommand
from prism.cli.repo import ACTIVE_TEST_FILE, TEST_RUN_PATH


def monitor_parser(parser):
    parser.add_argument("--replay", action="store_true", help="Parse the replay/receive.log files.")
    parser.add_argument("--verbose", action="store_true", help="Print verbose statistics.")
    parser.add_argument("--debug", action="store_true", help="Debug mode: Do not clear the screen when reporting.")
    parser.add_argument("--dir", help="Watch a specific directory.")


def get_test_dir(args):
    if args.dir:
        p = Path(args.dir)
        if not p.exists():
            return None, None
        return p, p / ".restart_monitor"

    if not ACTIVE_TEST_FILE.exists():
        return None, None

    test_dir = TEST_RUN_PATH / ACTIVE_TEST_FILE.read_text().strip()

    if not test_dir.exists():
        return None, None

    return test_dir / "logs", ACTIVE_TEST_FILE


def monitor(args):
    from prism.monitor import Monitor, DirectoryReader, MONITOR_FILES, REPLAY_FILES

    try:
        while True:
            test_dir, restart_file = get_test_dir(args)

            if not test_dir:
                time.sleep(1)
                continue

            test_files = MONITOR_FILES.copy()
            if args.replay:
                test_files.update(REPLAY_FILES)

            reader = DirectoryReader(test_dir, test_files)

            mon = Monitor(
                reader,
                replay=args.replay,
                verbose=args.verbose,
                debug=args.debug,
                clear_file=restart_file
            )
            trio.run(mon.run)
    except KeyboardInterrupt:
        return


cli_command = CLICommand(
    "monitor",
    monitor_parser,
    monitor,
    help="Monitor the active test deployment.",
    aliases=["mon"]
)
