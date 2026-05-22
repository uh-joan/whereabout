from __future__ import annotations
from abc import ABC, abstractmethod
from whereabout.models import RawEvent, Query


class BaseSource(ABC):
    source_id: str
    live: bool = True

    @abstractmethod
    async def fetch(self, query: Query) -> list[RawEvent]:
        """Fetch events matching the query. Returns normalised RawEvent list."""
        ...
