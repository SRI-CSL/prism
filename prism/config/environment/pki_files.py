#  Copyright (c) 2019-2023 SRI International.
from pathlib import Path
from typing import *

from prism.common.crypto.halfkey.rsa import RSAPrivateKey, KeyCertificatePair
from prism.config.config import Configuration


# creating PKI files to simulate PRISM Root CA (Server Registration Committee) at runtime

def create_server_file(root_pair: KeyCertificatePair, keys_dir: Path, prefix: str):
    server_pair = KeyCertificatePair(root_pair.key, private_key=RSAPrivateKey(), issuer=root_pair.cert.issuer)
    server_pair.dump(open(keys_dir / f"{prefix}_pair.json", "w"))


def generate_pki(config: Configuration, keys_dir: Path = None, prefix: str = "") \
        -> Tuple[Optional[KeyCertificatePair], List[str]]:
    """Generate PKI (approximation) and write as files to configuration directory if requested."""
    epoch_prefixes = []
    root_pair = None
    if config.pki:
        # generate root cert and key:
        root_pair = KeyCertificatePair(RSAPrivateKey())
        config.set_path(["prism_common", "pki_root_cert"], root_pair.cert_bytes.decode("utf-8"))
        # root_key_file = ""
        if config.pki_epochs == 0:
            # also set root key in server common
            config.set_path(["server_common", "pki_root_key"], root_pair.key.serialize().decode("utf-8"))
            # save root key as well:
            # root_path.write_bytes(root_pair.key.serialize())
            # print(f" ~~~ Written Root key to file {root_path}")
            # root_key_file = prefix + root_path.name
        else:
            config.set_path(["server_common", "pki_epochs"], config.pki_epochs)
            # if keys_dir:
            #     keys_dir.mkdir(exist_ok=True, parents=True)
            #     # # TODO: don't write root pair to file anymore...
            #     # cert_path = keys_dir / "root_cert.pem"
            #     # cert_path.write_bytes(root_pair.cert_bytes)
            #     # print(f" ~~~ Written Root CA certificate to file {cert_path}")
            #     # root_path = keys_dir / "root_key.pem"

            # root_path.unlink(missing_ok=True)
            # config.set_path(["server_common", "pki_root_private_key_file"], root_key_file)

        # return stub paths to be completed differently later by Testbed and RiB deployments:
        for epoch_i in range(config.pki_epochs):
            # for each pre-configured epoch, generate parent dir "epoch_NNN"
            epoch_prefixes.append(f"epoch-{epoch_i:03d}")

    return root_pair, epoch_prefixes
