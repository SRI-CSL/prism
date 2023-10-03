#  Copyright (c) 2019-2023 SRI International.
from prism.common.config import init_config, module_config_path
from prism.common.logging import init_logging, configure_logging
from prism.common.state import DummyStateStore
from prism.common.transport.prism_transport import PrismTransport
from prism.common.config import configuration
from prism.server.newserver import PrismServer


# @trio.testing.trio_test
def test_server():
    init_logging()
    init_config(None, [])
    configure_logging("prism.server", configuration)
    transport = PrismTransport(configuration)
    prism = PrismServer(transport, DummyStateStore())
    # from prism.common.config import configuration
    # self.assertTrue(configuration.debug)
    assert isinstance(prism, PrismServer), "is a PRISM server"
    # try:
    #     trio.run(prism.main)
    # except KeyboardInterrupt:
    #     pass
