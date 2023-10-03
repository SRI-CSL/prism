#  Copyright (c) 2019-2023 SRI International.

import argparse

parser = argparse.ArgumentParser(description="Generate Testbed Config Files")
required = parser.add_argument_group("Required Arguments")
optional = parser.add_argument_group("Optional Arguments")

# Required arguments
required.add_argument(
    "-o",
    "--output",
    dest="output_path",
    help="The directory to write configuration files to.",
    required=True,
    type=str,
)

# Optional Arguments
optional.add_argument(
    "--clients",
    dest="client_count",
    help="The number of clients in the testbed (default=2).",
    default=2,
    type=int,
)
optional.add_argument(
    "--servers",
    dest="server_count",
    help="The number of servers in the testbed (default=6).",
    default=6,
    type=int,
)
optional.add_argument(
    "--bebos",
    dest="bebo_count",
    help="The number of bebos in the testbed (default=1).",
    default=1,
    type=int,
)

optional.add_argument(
    "--param",
    "-P",
    metavar="PARAM=VALUE",
    action="append",
    dest="param_overrides",
    default=[],
    help="Override a config parameter. May be specified multiple times.\nExample: -Ptopology=SPARSE_ROUTED",
)

optional.add_argument(
    "--cached-ibe",
    action="store_true",
    help="Use the built-in IBE cache to speed up generation of deployments with 1000 or fewer clients."
)

parser.add_argument(
    "json_configs", metavar="JSON", type=argparse.FileType("r"), nargs="*", help="JSON configuration files."
)
