
#  Copyright (c) 2019-2023 SRI International.

import os
import pytest
import socket
import bebo.util as bu

def test_af_for_text_address():
    assert bu.af_for_text_address('127.0.0.1') == socket.AF_INET
    assert bu.af_for_text_address('::1') == socket.AF_INET6

def test_to_binary_address():
    assert bu.to_binary_address('127.0.0.1') == b'\x7f\x00\x00\x01'
    assert bu.to_binary_address('::1') == b'\x00' * 15 + b'\x01'

def test_to_text_address():
    assert bu.to_text_address(b'\x7f\x00\x00\x01') == '127.0.0.1'
    assert bu.to_text_address(b'\x00' * 15 + b'\x01') == '::1'

def test_is_text_address():
    assert not bu.is_text_address(False)
    assert not bu.is_text_address('bogus')
    assert bu.is_text_address('127.0.0.1')
    assert bu.is_text_address('::1')

def test_hostify():
    assert bu.hostify('1') == '10.53.0.1'
    assert bu.hostify(1) == '10.53.0.1'
    assert bu.hostify('1', False, True) == 'fd53::1'
    assert bu.hostify('1.2.3.4', True, False) == '1.2.3.4'
    assert bu.hostify('::1', False, True) == '::1'
    assert bu.hostify('f.root-servers.net', True, False) == '192.5.5.241'
    # Do not test IPv6 here as our use of AI_ADDRCONFIG will cause it
    # to fail on a system without fully working IPv6.
    #assert bu.hostify('f.root-servers.net', False, True) == \
    #    '2001:500:2f::f'

def test_get_boolean_env():
    try:
        del os.environ['FOO']
    except KeyError:
        pass
    assert bu.get_boolean_env('FOO') == False
    os.environ['FOO'] = '123'
    assert bu.get_boolean_env('FOO') == True
    os.environ['FOO'] = '0'
    assert bu.get_boolean_env('FOO') == False
    os.environ['FOO'] = 'FaLsE'
    assert bu.get_boolean_env('FOO') == False
    os.environ['FOO'] = 'no'
    assert bu.get_boolean_env('FOO') == False
    del os.environ['FOO']

def test_get_int_env():
    try:
        del os.environ['FOO']
    except KeyError:
        pass
    assert bu.get_int_env('FOO', 1234) == 1234
    os.environ['FOO'] = '123'
    assert bu.get_int_env('FOO', 0) == 123
    os.environ['FOO'] = 'abc'
    with pytest.raises(ValueError):
        bu.get_int_env('FOO', 0)
    del os.environ['FOO']
