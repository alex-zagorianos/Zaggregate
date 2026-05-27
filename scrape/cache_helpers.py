import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from config import CACHE_TTL_HOURS


def read_cache(cache_file: Path) -> Optional[Any]:
    if not cache_file.exists():
        return None
    age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
    if age > timedelta(hours=CACHE_TTL_HOURS):
        return None
    with open(cache_file, "r", encoding="utf-8") as f:
        content = f.read()
    if cache_file.suffix == ".json":
        return json.loads(content)
    return content


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
    return text.lower().replace(" ", "_").replace("/", "_").replace(",", "").replace('"', "")
