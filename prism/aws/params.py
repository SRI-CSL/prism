#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import *


@dataclass
class AWSParams:
    """
    This class defines parameters used specifically by PRISM deployed to AWS.
    PRISM system parameters are defined in the module prism.config.config
    """
    regions: List[str] = field(default_factory=lambda: ["us-east-1", "us-east-2", "us-west-2"])

    # number of Bebo instances per region
    bebo_per_region: int = field(default=2)

    # how to connect Bebo instances within one region
    bebo_strategy: str = field(default="FULLY")  # "RING" or "FULLY" or TODO: "SPARSE"

    # whether Bebo can use IPv6 or not; it seems that some docker deployments don't have dual-stack and cannot mix
    # IPv4 and IPv6 TCP channels amongst them (e.g., for "head" of region that connects to other regions)
    bebo_ip_v6: bool = field(default=False)

    # list of client names and their region string
    clients: List[List[str, str]] = field(default_factory=list)

    # number of clients if we want to generate them using a template like "prism-client-00001" etc.
    n_clients: int = 0

    dropbox_count: int = field(default=1)

    wbs: List = field(default_factory=list)

    pki_root_cert: str = None

    public_params: str = None

    test_indices: List[str] = field(default_factory=list)

    batches: Dict[int, int] = field(default_factory=dict)

    # A catch-all for overrides this class doesn't know about, which
    # will be passed to the configuration generator.
    overrides: dict = field(default_factory=dict)

    def to_json(self):
        return vars(self)

    @staticmethod
    def load_args(args) -> AWSParams:
        params = AWSParams()

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

        # # Add parameters to args that prism.config.config.Configuration will look for
        # args.client_count = params.client_count
        # args.server_count = params.server_count
        # args.bebo_count = params.bebo_count
        args.param_overrides = [f"{k}={v}" for k, v in params.overrides.items()]
        args.json_configs = []
        # args.ibe_cache = None
        # args.cached_ibe = False

        return params
