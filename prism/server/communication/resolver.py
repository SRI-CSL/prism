#  Copyright (c) 2019-2023 SRI International.
from abc import ABCMeta
from typing import Dict, List, Tuple, KeysView, Set, Union


class ResolverInterface(metaclass=ABCMeta):
    """
    An abstract class defining the API for resolving A-things to pseudonyms (as strings) and looking up the reverse.

    Symmetric dictionary from https://stackoverflow.com/a/26082413/3816489 that allows us to save the tightly
    connected relationship between peer index, persona name, etc. and pseudonyms as addresses in PRISM.
    """

    def __init__(self, own_entries: List[Tuple[Union[int, str], str]]) -> None:
        super().__init__()
        self._a_to_pseudonym = {}  # type: Dict[Union[int, str], str]
        self._pseudonym_to_a = {}  # type: Dict[str, Union[int, str]]
        self.update(own_entries)

    def update(self, bindings: List[Tuple[Union[int, str], str]]):
        for a, b in bindings:
            self.associate(a, b)

    def associate(self, a, pseudonym: str) -> Tuple[Union[int, str], str]:
        # stores and returns a tuple of overwritten binding (if it existed before)
        current_pseudonym = self._a_to_pseudonym.get(a, None)
        current_a = self._pseudonym_to_a.get(pseudonym, None)
        self._a_to_pseudonym[a] = pseudonym
        self._pseudonym_to_a[pseudonym] = a
        return current_a, current_pseudonym

    def resolve(self, something_a: Union[int, str]):
        return self._a_to_pseudonym.get(something_a)

    def resolve_multiple(self, somethings: List[Union[int, str]]) -> List[str]:
        return list(map(self.resolve, somethings))

    def somethings(self) -> KeysView[Union[int, str]]:
        return self._a_to_pseudonym.keys()

    def lookup(self, pseudonym: str) -> Union[int, str]:
        return self._pseudonym_to_a.get(pseudonym)

    def pseudonyms(self) -> KeysView[str]:
        return self._pseudonym_to_a.keys()


# TODO: do we need some methods async and have a Trio.Lock guarding them as different tasks access this data structure?
class PeerResolver(ResolverInterface):
    def __init__(self, own_entries: List[Tuple[int, str]] = None):
        super().__init__(own_entries)
        self._own_indices, self._own_pseudonyms = map(set, zip(*own_entries)) if own_entries else (set(), set())

    @property
    def own_indices(self) -> Set[int]:
        return self._own_indices

    @property
    def own_pseudonyms(self) -> Set[str]:
        return self._own_pseudonyms


class AddressResolver(ResolverInterface):

    def __init__(self, own_entries: List[Tuple[str, str]] = None):
        super().__init__(own_entries)

    def all_resolvable(self, addresses: List[str]) -> bool:
        return all(a in self._a_to_pseudonym for a in addresses)