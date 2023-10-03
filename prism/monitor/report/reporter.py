#  Copyright (c) 2019-2023 SRI International.
import io
import os
from contextlib import redirect_stdout

import trio

from .deployment import Deployment


class PrintReporter:
    """Prints the latest report to stdout on a specified interval."""

    def __init__(self, deployment: Deployment, interval: float, clear=True, verbose=False):
        self.deployment = deployment
        self.report_interval_s = interval
        self.clear = clear
        self.verbose = verbose

    async def run(self):
        while True:
            report = self.deployment.generate_report(verbose=self.verbose)
            with io.StringIO() as buf, redirect_stdout(buf):
                report.print_report()
                report_str = buf.getvalue()

            if self.clear:
                os.system("clear")

            print(report_str)

            await trio.sleep(self.report_interval_s)
