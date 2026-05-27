import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class JobResult:
    title: str
    company: str
    location: str
    salary_min: Optional[float]
    salary_max: Optional[float]
    description: str
    url: str
    source_keyword: str
    created: str
    job_id: str = ""
    source_api: str = ""

    @property
    def dedup_key(self) -> str:
        raw = f"{(self.title or '').lower().strip()}|{(self.company or '').lower().strip()}|{(self.location or '').lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    def salary_display(self) -> str:
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,.0f} - ${self.salary_max:,.0f}"
        if self.salary_min:
            return f"${self.salary_min:,.0f}+"
        return "Not listed"
