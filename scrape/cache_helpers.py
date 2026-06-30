import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from config import CACHE_TTL_HOURS, FAILED_TTL_HOURS

# Characters that are illegal in Windows filenames (": " breaks Workday slugs
# like "cat:5:CaterpillarCareers" -> [Errno 22] Invalid argument).
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*,\s]+')


def read_cache(cache_file: Path, ttl_hours: float = CACHE_TTL_HOURS) -> Optional[Any]:
    if not cache_file.exists():
        return None
    age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
    if age > timedelta(hours=ttl_hours):
        return None
    with open(cache_file, "r", encoding="utf-8") as f:
        content = f.read()
    if cache_file.suffix == ".json":
        return json.loads(content)
    return content


def read_failed(failed_file: Path) -> Optional[Any]:
    """Read a negative-cache "_FAILED" marker on the longer FAILED_TTL_HOURS
    window. Use with is_failed() so a known-dead URL is skipped for a week
    instead of being re-probed (at full request timeout) on every daily run."""
    return read_cache(failed_file, ttl_hours=FAILED_TTL_HOURS)


def write_cache(cache_file: Path, data: Any) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(cache_file.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, indent=2)
    os.replace(tmp, cache_file)


def slug_safe(text: str) -> str:
    return _UNSAFE_CHARS.sub("_", text.lower()).strip("_")


def mark_failed(cache_file: Path) -> None:
    """Negative-cache a fetch failure. Dead slugs (404/timeout) were retried
    for every keyword in a run — ~10 doomed requests per dead company per
    day. The marker makes it one attempt per TTL window."""
    write_cache(cache_file, {"_failed": True})


def is_failed(cached) -> bool:
    return isinstance(cached, dict) and cached.get("_failed") is True
