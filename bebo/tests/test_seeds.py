
#  Copyright (c) 2019-2023 SRI International.

from bebo.seeds import Seeds

def test_seeds():
    s = Seeds('seeds.json', '10.53.0.1')
    assert s.seeds == {'10.53.0.2', '10.53.0.3', '10.53.0.4', '10.53.0.5'}
    choices = s.choose(2)
    assert len(choices) == 2
    for choice in choices:
        assert choice in s.seeds

def test_choose_too_many():
    s = Seeds('seeds.json', '10.53.0.1')
    assert s.seeds == {'10.53.0.2', '10.53.0.3', '10.53.0.4', '10.53.0.5'}
    choices = s.choose(100)
    assert len(choices) == 4
    assert set(choices) == s.seeds
