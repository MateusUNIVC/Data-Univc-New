from __future__ import annotations

from abc import ABC, abstractmethod

from ..context import AdapterInput
from ..contract import WorkbookSpec


class DirectorateAdapter(ABC):
    """Boundary between domain data and Excel rendering.

    Adapters must be declarative: they translate authorized domain data into a
    WorkbookSpec. They must not create workbooks, styles, charts, or perform
    direct database/API access.
    """

    adapter_code: str
    adapter_version: int

    @abstractmethod
    def build_spec(self, adapter_input: AdapterInput) -> WorkbookSpec:
        raise NotImplementedError
