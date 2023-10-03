#  Copyright (c) 2019-2023 SRI International.
import pytest

from prism.common.state import DummyStateStore
from prism.server.CS2.roles.emix import Emix
from prism.server.CS2.roles.abstract_role import AbstractRole
from prism.server.server_data import ServerData
from prism.common.transport.prism_transport import PrismTransport
from prism.common.config import configuration, init_config


init_config(None, [])
serverdata = ServerData(id='my_ID',
                        certificate=b'',
                        DH_public_dict={},
                        pseudonym=b'pseudo',
                        role_name='EMIX-you guessed it',
                        committee='committee NAME',
                        epoch='genesis',
                        proof=None,
                        dropbox_index=None)


# def test_dropbox():
#     role = RoleFactory.create(role_name="DROPBOX", sd=serverdata)
#     assert isinstance(role, DropboxSS), "role is (single-server) Dropbox"


def test_emix():
    role1 = AbstractRole.create("emix",
                                transport=PrismTransport(configuration),
                                sd=serverdata,
                                state_store=DummyStateStore(),
                                role_keys=None,
                                previous_role=None,
                                )
    assert isinstance(role1, Emix), "role is Emix"
    role2 = AbstractRole.create("Emix",
                                transport=PrismTransport(configuration),
                                sd=serverdata,
                                state_store=DummyStateStore(),
                                role_keys=None,
                                previous_role=None,
                                )
    assert role1 != role2, "factory creates fresh instances of Roles"


def test_initializations():
    role = AbstractRole.create("emix",
                               transport=PrismTransport(configuration),
                               sd=serverdata,
                               state_store=DummyStateStore(),
                               role_keys=None,
                               previous_role=None,
                               )
    assert isinstance(role, Emix)


def test_not_exist():
    with pytest.raises(ValueError):
        AbstractRole.create("foo")

    with pytest.raises(ValueError):
        AbstractRole.create("UNDEFINED")
