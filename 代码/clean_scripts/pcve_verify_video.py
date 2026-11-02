"""Verify dimensions, timing, decoded frame count and full video decoding."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--resolution", type=int, nargs=2, default=(1280, 720))
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--frames", type=int, default=96)
    a = p.parse_args()
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames:format=duration",
        "-of", "json", str(a.video)], text=True))
    stream = probe["streams"][0]
    checks = {
        "resolution": [stream["width"], stream["height"]] == list(a.resolution),
        "fps": Fraction(stream["avg_frame_rate"]) == a.fps,
        "frames": int(stream["nb_read_frames"]) == a.frames,
        "duration": abs(float(probe["format"]["duration"]) - a.frames / a.fps) < 1 / a.fps,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Video specification mismatch: {checks}; {probe}")
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(a.video), "-f", "null", "-"], check=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(a.video.read_bytes()).hexdigest()
    a.out.write_text(json.dumps({"video": str(a.video.resolve()), "sha256": digest,
                                 "checks": checks, "probe": probe, "full_decode": True}, indent=2) + "\n")


if __name__ == "__main__":
    main()
