"""Read-only audit of the kitchen_can_collision suite: manifest, caches and frame counts."""
from __future__ import annotations

# PCVE_UNIFIED_ENTRY_BEGIN
import sys as _audit_sys
from pathlib import Path as _AuditPath
_SCENE_DIR = _AuditPath(__file__).resolve().parents[1]
for _sub in (_SCENE_DIR.parents[1], _SCENE_DIR, _SCENE_DIR / "physics", _SCENE_DIR / "appearance"):
    if _sub.is_dir() and str(_sub) not in _audit_sys.path:
        _audit_sys.path.insert(1, str(_sub))
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
from pathlib import Path

SCENE = "kitchen_can_collision"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, required=True, help="Suite root produced by build_pcve_%s.py" % SCENE)
    parser.add_argument("--json", type=Path, help="Write the full report here")
    args = parser.parse_args()

    root = args.out_root.resolve()
    manifest_path = root / "suite_manifest.json"
    report = {"scene": SCENE, "out_root": str(root), "passed": True, "errors": [], "cases": {}}
    if not manifest_path.is_file():
        report["passed"] = False
        report["errors"].append("missing suite_manifest.json")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = [manifest.get("source") or {}] + list(manifest.get("edits") or [])
        for record in records:
            case_id = record.get("case_id")
            if not case_id:
                continue
            folder = root / "cases" / case_id
            entry = {"case_dir": str(folder), "cache": False, "frames": 0, "video": (folder / "video.mp4").is_file()}
            cache = folder / "physics_transforms.json"
            if cache.is_file():
                try:
                    data = json.loads(cache.read_text(encoding="utf-8"))
                    entry["cache"] = True
                    entry["frames"] = len(data.get("frames") or [])
                    entry["frame_end"] = data.get("frame_end")
                    entry["quality_valid"] = bool((data.get("quality") or {}).get("valid", True))
                except Exception as exc:  # a broken cache is a finding, not a crash
                    entry["error"] = str(exc)
                    report["errors"].append("%s: %s" % (case_id, exc))
            else:
                report["errors"].append("%s: missing physics_transforms.json" % case_id)
            report["cases"][case_id] = entry
        if not report["cases"]:
            report["errors"].append("suite_manifest.json lists no cases")
    report["passed"] = not report["errors"]
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "cases": len(report["cases"]), "errors": report["errors"]}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
