#  Copyright (c) 2019-2023 SRI International.

import datetime
import json
import sys
import time
from pathlib import Path

import trio

from prism.cli.repo import TEST_RUN_PATH, ACTIVE_TEST_FILE
from prism.config.environment.testbed import generate_config
from prism.testbed.backend.docker import DockerBackend
from prism.testbed.params import TestParams
from prism.testbed.report import generate_report, present, serialize_test_object
from prism.testbed.testbed import run_test


def main(args):
    par = TestParams.load_args(args)

    if not args.output_path:
        if args.timestamped and not args.no_config:
            now = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            args.output_path = str(TEST_RUN_PATH / f"{par.project}-{now}")
        else:
            args.output_path = str(TEST_RUN_PATH / "current")

    if args.no_config:
        deployment = None
        run_path = Path(args.output_path)
        args.no_test = True
    else:
        deployment = generate_config(args)
        run_path = deployment.output_path

    log_path = run_path / "logs"

    if args.generate:
        print(run_path)
        return

    if args.build:
        from prism.cli.build import empty_args, build_images
        build_images(empty_args())

    ACTIVE_TEST_FILE.write_text(run_path.name)

    if args.no_test or par.web_client:
        backend = DockerBackend(par, run_path / "docker-compose.json")
        with backend:
            try:
                while True:
                    time.sleep(5)
            except KeyboardInterrupt:
                return

    try:
        results = trio.run(run_test, par, deployment)

        with open(log_path / 'raw_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=serialize_test_object)

        rep = generate_report(results)

        with open(log_path / 'report.json', 'w') as f:
            json.dump(rep, f, indent=2, default=serialize_test_object)

        present(rep)

        if rep['dropped'] > 0:
            sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(1)
    finally:
        ACTIVE_TEST_FILE.unlink(missing_ok=True)
