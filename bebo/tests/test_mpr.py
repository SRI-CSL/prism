
#  Copyright (c) 2019-2023 SRI International.

from bebo.storage import Storage
from bebo.server import Server, Neighbor

def test_basic_isolated():
    n2 = Neighbor('10.53.0.2', ['10.53.0.5'])
    n3 = Neighbor('10.53.0.3', ['10.53.0.6', '10.53.0.7'])
    n4 = Neighbor('10.53.0.4', ['10.53.0.7'])
    s = Server(Storage())
    s.host = '10.53.0.1'
    s.neighbors[n2.address] = n2
    s.neighbors[n3.address] = n3
    s.neighbors[n4.address] = n4
    s.compute_mpr()
    assert s.mpr == {'10.53.0.2', '10.53.0.3'}

def test_basic_max_coverage():
    # same test as test_basic(), but with the roles of n3 and n4
    # exchanged to rule out any accidental failure hiding due to dict
    # order.
    n2 = Neighbor('10.53.0.2', ['10.53.0.5'])
    n3 = Neighbor('10.53.0.3', ['10.53.0.5', '10.53.0.6', '10.53.0.7'])
    n4 = Neighbor('10.53.0.4', ['10.53.0.6', '10.53.0.7'])
    s = Server(Storage())
    s.host = '10.53.0.1'
    s.neighbors[n2.address] = n2
    s.neighbors[n3.address] = n3
    s.neighbors[n4.address] = n4
    s.compute_mpr()
    assert s.mpr == {'10.53.0.3'}

def test_ignore_me():
    n2 = Neighbor('10.53.0.2', ['10.53.0.5'])
    n3 = Neighbor('10.53.0.3', ['10.53.0.6', '10.53.0.7'])
    n4 = Neighbor('10.53.0.4', ['10.53.0.7', '10.53.0.1'])
    s = Server(Storage())
    s.host = '10.53.0.1'
    s.neighbors[n2.address] = n2
    s.neighbors[n3.address] = n3
    s.neighbors[n4.address] = n4
    s.compute_mpr()
    assert s.mpr == {'10.53.0.2', '10.53.0.3'}

def test_ignore_one_hop():
    n2 = Neighbor('10.53.0.2', ['10.53.0.3'])
    n3 = Neighbor('10.53.0.3', ['10.53.0.6', '10.53.0.7'])
    n4 = Neighbor('10.53.0.4', ['10.53.0.7', '10.53.0.1'])
    s = Server(Storage())
    s.host = '10.53.0.1'
    s.neighbors[n2.address] = n2
    s.neighbors[n3.address] = n3
    s.neighbors[n4.address] = n4
    s.compute_mpr()
    assert s.mpr == {'10.53.0.3'}
