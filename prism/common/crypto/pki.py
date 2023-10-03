#  Copyright (c) 2019-2023 SRI International.
import structlog

from prism.common.crypto.halfkey.rsa import cert_from_json_str


class CommonPKI:
    def __init__(self, config):
        self.logger = structlog.get_logger(__name__ + ' > ' + self.__class__.__name__)
        self.root_cert = None
        # load PRISM Root CA (if configured)
        root_cert_decoded = config.get("pki_root_cert", "")
        if root_cert_decoded:
            self.root_cert = cert_from_json_str(root_cert_decoded)
            self.logger.debug(f"Created PRISM Root CA cert from config")
