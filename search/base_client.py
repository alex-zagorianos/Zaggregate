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
