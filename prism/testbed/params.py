#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class TestParams:
    """
    This class defines parameters used specifically by the testbed.
    PRISM system parameters are defined in the module prism.config.config
    """
    # Used in docker compose file generation, as well as for naming the test run
    # directory if you don't specify one.
    project: str = field(default="prism-integration")

    # After the test finishes running, keeps the containers up for inspection
    # until you hit Enter.
    pause_before_exit: bool = field(default=False)

    # Runs clients in web mode. Disables automated testing.
    web_client: bool = field(default=False)

    # The time (in seconds) to wait after all messages have been sent.
    timeout: int = field(default=120)

    # How many messages to send between each pair of clients
    messages_per_pair: int = field(default=5)

    # How many seconds to wait in between sending messages
    message_delay_seconds: float = field(default=1.0)

    # The length of messages, in bytes
    message_length: int = field(default=140)

    # The number of clients in the deployment
    client_count: int = field(default=2)

    # The number of servers in the deployment
    server_count: int = field(default=6)

    # The number of BEBO whiteboards serving the deployment
    bebo_count: int = field(default=1)

    # A catch-all for overrides this class doesn't know about, which
    # will be passed to the configuration generator.
    overrides: dict = field(default_factory=dict)

    def to_json(self):
        return vars(self)

    @staticmethod
    def load_args(args) -> TestParams:
        params = TestParams()

        for scenario in args.scenarios:
            j = json.load(scenario)

            for k, v in j.items():
                if not hasattr(params, k):
                    continue
                if k == "overrides":
                    params.overrides.update(v)
                else:
                    setattr(params, k, v)

        for override in args.param_overrides:
            k, v = override.split("=", 1)

            if hasattr(params, k):
                atype = type(getattr(params, k))
                newval = atype(v)
                setattr(params, k, newval)
            else:
                params.overrides[k] = v

        # Add parameters to args that prism.config.config.Configuration will look for
        args.client_count = params.client_count
        args.server_count = params.server_count
        args.bebo_count = params.bebo_count
        args.param_overrides = [f"{k}={v}" for k, v in params.overrides.items()]
        args.json_configs = []
        args.ibe_cache = None
        args.cached_ibe = False

        return params
