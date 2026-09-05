from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple

import pandas as pd


class BaseStrategy(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[str], dict[str, Any]]:
        ...
