#  Copyright (c) 2019-2023 SRI International.

import json

from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Optional


class StateStore(metaclass=ABCMeta):
    @abstractmethod
    def save_state(self, name: str, state: dict):
        pass

    @abstractmethod
    def load_state(self, name: str) -> Optional[dict]:
        pass


class DummyStateStore(StateStore):
    def __init__(self):
        super().__init__()
        self.state = {}

    def save_state(self, name: str, state: dict):
        self.state[name] = state

    def load_state(self, name: str) -> Optional[dict]:
        return self.state.get(name, None)


class DirectoryStateStore(StateStore):
    def __init__(self, state_path: Path):
        super().__init__()
        self.state_path = state_path
        self.state_path.mkdir(exist_ok=True)

    def save_path(self, name: str) -> Path:
        return self.state_path / f"{name}.json"

    def save_state(self, name: str, state: dict):
        self.save_path(name).write_text(json.dumps(state))

    def load_state(self, name: str) -> Optional[dict]:
        if not self.save_path(name).exists():
            return None

        return json.loads(self.save_path(name).read_text())
