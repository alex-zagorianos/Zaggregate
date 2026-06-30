from abc import ABC, abstractmethod
from typing import Optional

from models import JobResult


class JobAPIClient(ABC):
    @abstractmethod
    def search(
        self,
        keyword: str,
        location: str,
        salary_min: Optional[int],
        page: int,
    ) -> dict: ...

    @abstractmethod
    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]: ...

    def search_and_parse(
        self,
        keyword: str,
        location: str,
        salary_min: Optional[int],
        page: int,
    ) -> list[JobResult]:
        """Combined search+parse. Override to skip the dict roundtrip."""
        raw = self.search(keyword=keyword, location=location,
                          salary_min=salary_min, page=page)
        return self.parse_results(raw, keyword)
