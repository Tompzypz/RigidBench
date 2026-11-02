"""Path helpers shared by standalone rigid-scene folders."""
from pathlib import Path
import sys


def project_root(anchor):
    anchor = Path(anchor).resolve()
    candidates = (anchor, *anchor.parents)
    for candidate in candidates:
        if (candidate / "assets").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    raise FileNotFoundError(f"Cannot locate project root above {anchor}; expected assets/ and scripts/")


def scene_root(anchor):
    """Find the scene folder from argv first, then from the helper's parents."""
    candidates = []
    if sys.argv and sys.argv[0] not in {"-", ""}:
        argv_path = Path(sys.argv[0]).expanduser()
        if not argv_path.is_absolute():
            argv_path = Path.cwd() / argv_path
        candidates.append(argv_path.resolve().parent)
    anchor = Path(anchor).resolve()
    candidates.extend(anchor.parents)
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if any(candidate.glob("simulate_*.py")) and any(candidate.glob("render_*.py")):
            return candidate
    raise FileNotFoundError(f"Cannot locate scene entrypoints above {anchor}")
