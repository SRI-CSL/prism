
#  Copyright (c) 2019-2023 SRI International.

import pytest

import bebo.protocol as BP

# General testing

def test_not_dict():
    with pytest.raises(SyntaxError):
        BP.from_python(['hi'])
    with pytest.raises(SyntaxError):
        BP.from_python(1)

def test_no_type():
    with pytest.raises(SyntaxError):
        BP.from_python({100: 'bar'})

def test_unknown_type():
    with pytest.raises(SyntaxError):
        BP.from_python({1: 100})

# HandshakeMessage

def test_handshake():
    m1 = BP.HandshakeMessage()
    m2 = BP.from_cbor(m1.to_cbor())
    assert isinstance(m2, BP.HandshakeMessage)
    assert m1.error == m2.error
    assert m1.error is None
    m1 = BP.HandshakeMessage('badness')
    m2 = BP.from_cbor(m1.to_cbor())
    assert isinstance(m2, BP.HandshakeMessage)
    assert m1.error == m2.error
    assert m1.error == 'badness'

def test_handshake_bad_error():
    with pytest.raises(SyntaxError):
        BP.from_python({1: 1, 5: 30})

# RelayMessage

def test_relay():
    m1 = BP.RelayMessage(b'hello')
    m2 = BP.from_cbor(m1.to_cbor())
    assert isinstance(m2, BP.RelayMessage)
    assert m1.message == m2.message
    assert m1.broadcast == m2.broadcast
    assert m1.broadcast
    m1 = BP.RelayMessage(b'world', False)
    m2 = BP.from_cbor(m1.to_cbor())
    assert isinstance(m2, BP.RelayMessage)
    assert m1.message == m2.message
    assert m1.broadcast == m2.broadcast
    assert not m1.broadcast

def test_relay_message_size():
    m = BP.RelayMessage(b'hello')
    assert m.size() == 5

def test_relay_message_key():
    m = BP.RelayMessage(b'hello')
    assert m.key() == \
        '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'

def test_relay_to_json():
    m = BP.RelayMessage(b'hello')
    assert m.to_json() == 'aGVsbG8='

def test_relay_no_message():
    with pytest.raises(SyntaxError):
        BP.from_python({1: 2})

def test_relay_bad_message():
    with pytest.raises(SyntaxError):
        BP.from_python({1: 2, 2: 30})

def test_relay_bad_broadcast():
    with pytest.raises(SyntaxError):
        BP.from_python({1: 2, 2: b'hi', 3: 30})

# NeighborsMessage

def test_neighbors():
    m1 = BP.NeighborsMessage(['10.0.0.1', '10.0.0.2'])
    m2 = BP.from_cbor(m1.to_cbor())
    assert isinstance(m2, BP.NeighborsMessage)
    assert m1.neighbors == m2.neighbors

def test_neighbors_no_neighbors():
    with pytest.raises(SyntaxError):
        BP.from_python({1: 3})

def test_neighbors_bad_neighbors():
    with pytest.raises(SyntaxError):
        BP.from_python({1: 3, 4: 1})
    with pytest.raises(SyntaxError):
        BP.from_python({1: 3, 4: ['10.0.0.1']})
    with pytest.raises(SyntaxError):
        BP.from_python({1: 3, 4: [b'\x0a\x00\x01']})
