import json
import os
from pathlib import Path
from typing import Any, Optional

SNAPSHOT_MODE = os.getenv("SNAPSHOT_MODE", "false").strip().lower() in ("true", "1", "yes")

SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent / "snapshots"

ALLOWED_DAYS = [30, 90, 365]
ALLOWED_LEAD_DAYS = [3, 5, 7, 10]
ALLOWED_COVER_DAYS = [7, 14, 21, 30]
ALLOWED_GRANULARITIES = ["day", "week", "month"]

_SNAPSHOT_CACHE: dict[str, Any] = {}
_MANIFEST: dict[str, Any] = {}
_INITIALIZED: bool = False


def is_snapshot_mode() -> bool:
    """Return True if SNAPSHOT_MODE environment variable is enabled."""
    return os.getenv("SNAPSHOT_MODE", "false").strip().lower() in ("true", "1", "yes")


def normalize_days(days: int) -> int:
    """Normalize days to nearest of 30, 90, 365 (0 only when days is 0)."""
    if days == 0:
        return 0
    return min(ALLOWED_DAYS, key=lambda x: abs(x - days))


def normalize_lead_days(lead_days: int) -> int:
    """Normalize delivery lead days to nearest of 3, 5, 7, 10."""
    return min(ALLOWED_LEAD_DAYS, key=lambda x: abs(x - lead_days))


def normalize_cover_days(cover_days: int) -> int:
    """Normalize days of stock cover to nearest of 7, 14, 21, 30."""
    return min(ALLOWED_COVER_DAYS, key=lambda x: abs(x - cover_days))


def normalize_granularity(granularity: str) -> str:
    """Normalize granularity to day, week, or month."""
    g = (granularity or "week").strip().lower()
    return g if g in ALLOWED_GRANULARITIES else "week"


def init_snapshots() -> None:
    """Read all precomputed snapshot JSON and CSV files once into memory."""
    global _SNAPSHOT_CACHE, _MANIFEST, _INITIALIZED
    if not is_snapshot_mode():
        return
    if not SNAPSHOTS_DIR.exists():
        return

    manifest_path = SNAPSHOTS_DIR / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            _MANIFEST = json.load(f)

    for p in SNAPSHOTS_DIR.glob("*"):
        if p.name == "manifest.json":
            continue
        try:
            if p.suffix == ".json":
                with open(p, "r", encoding="utf-8") as f:
                    _SNAPSHOT_CACHE[p.name] = json.load(f)
            elif p.suffix == ".csv":
                with open(p, "r", encoding="utf-8") as f:
                    _SNAPSHOT_CACHE[p.name] = f.read()
        except Exception:
            pass
    _INITIALIZED = True


def get_snapshot(filename: str) -> Optional[Any]:
    """Retrieve precomputed snapshot from in-memory cache."""
    global _INITIALIZED
    if not _INITIALIZED and is_snapshot_mode():
        init_snapshots()
    return _SNAPSHOT_CACHE.get(filename)


def get_manifest() -> dict[str, Any]:
    """Return parsed manifest containing metadata and snapshot timestamp."""
    global _INITIALIZED
    if not _INITIALIZED and is_snapshot_mode():
        init_snapshots()
    return _MANIFEST


# Preload in-memory cache if running in snapshot mode
if is_snapshot_mode():
    init_snapshots()

