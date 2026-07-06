from pathlib import Path
from config import DATA_DIR  # bundled, read-only

DATA_STATIC = Path(DATA_DIR) / "data_static"

def static_path(name: str) -> Path:
    return DATA_STATIC / name
