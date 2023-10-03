#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path
import sys
import trio
# local imports:
from prism.common.logging import init_logging, configure_logging
from prism.common.state import DummyStateStore
from prism.common.transport.prism_transport import PrismTransport
from prism.common.config import configuration, init_config
from prism.server.newserver import PrismServer

init_logging()
init_config(config_json=None, files=[Path(s) for s in sys.argv[1:]])
configure_logging("prism.server", configuration)
transport = PrismTransport(configuration)
prism = PrismServer(transport, DummyStateStore())
try:
    trio.run(prism.main)
except KeyboardInterrupt:
    pass
