"""Small process runner for scene-owned build_pcve entry points.

Plans are read-only under --dry-run. Existing unowned output directories and
completed stage products are never overwritten. Solver settings live in the
scene modules, not in this shared runner.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLENDER = Path.home() / ".local/opt/blender-4.3.2-linux-x64/blender"


@dataclass
class Step:
    name: str
    stage: str
    command: list
    outputs: tuple = ()
    env: dict = field(default_factory=dict)


def cli_args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def positive_integer(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def parser(description, python_env=".venv-genesis-mpm-sph", output_alias=False):
    p = argparse.ArgumentParser(description=description)
    output_options = ("--out-root", "--out-dir") if output_alias else ("--out-root",)
    p.add_argument(*output_options, type=Path, required=True, help="Fresh pipeline output root")
    p.add_argument("--stage", choices=("all", "prepare", "simulate", "surface", "render", "verify", "edits"), default="all")
    p.add_argument("--python", type=Path, default=ROOT / python_env / "bin/python")
    p.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    p.add_argument("--threads", type=positive_integer, default=8)
    p.add_argument("--gpu", help="An idle GPU index/UUID; otherwise inherit the runtime selection")
    p.add_argument("--dry-run", action="store_true", help="Print the complete command plan without creating files")
    return p


def blender(args, script, *options, scene=None):
    command = [args.blender, "-b"]
    if scene is not None:
        command.append(scene)
    return command + ["-t", str(args.threads), "--python-exit-code", "1", "--python", script, "--", *options]


def below(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def execute(scene, args, steps, inputs=()):
    root = args.out_root.expanduser().resolve()
    for step in steps:
        step.command = [value.expanduser().resolve()
                        if isinstance(value, Path) and (index > 0 or value.is_absolute() or len(value.parts) > 1)
                        else value for index, value in enumerate(step.command)]
    selected = [s for s in steps if args.stage == "all" or s.stage == args.stage]
    if not selected:
        raise ValueError(f"No {args.stage!r} stage in this pipeline")
    plan = [{"name": s.name, "stage": s.stage,
             "command": list(map(str, s.command)),
             "outputs": list(map(str, s.outputs)), "env": s.env} for s in steps]
    identity = {"scene": scene, "out_root": str(root), "plan": plan,
                "inputs": [str(Path(p).expanduser().resolve()) for p in inputs], "gpu": args.gpu}
    if args.dry_run:
        print(json.dumps({**identity, "dry_run": True, "selected_stage": args.stage}, indent=2))
        return
    if below(root, ROOT / "scripts"):
        raise ValueError("Runtime products must stay outside scripts/")
    for item in inputs:
        path = Path(item).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        if below(path, root) or (path.is_dir() and below(root, path)):
            raise ValueError(f"Output and read-only input overlap: {path}")
    for step in selected:
        program = Path(step.command[0])
        if program.is_absolute() and not program.is_file():
            raise FileNotFoundError(program)
        for token in map(str, step.command[1:]):
            if token.endswith((".py", ".sh")) and Path(token).is_absolute() and not Path(token).is_file():
                raise FileNotFoundError(token)
    manifest = root / "pipeline_manifest.json"
    if root.exists() and any(root.iterdir()):
        if not manifest.is_file():
            raise FileExistsError(f"Refusing an existing unowned output root: {root}")
        previous = json.loads(manifest.read_text())
        if previous.get("identity") != identity:
            raise ValueError("Existing pipeline parameters differ; choose a fresh --out-root")
        if args.stage == "all":
            raise FileExistsError("Use a fresh root for a full run; --stage can run a missing stage")
    else:
        previous = {}
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    state = {"identity": identity, "status": "running", "steps": previous.get("steps", {})}

    def save():
        temp = manifest.with_suffix(".json.tmp")
        temp.write_text(json.dumps(state, indent=2) + "\n")
        temp.replace(manifest)

    save()
    try:
        for step in selected:
            if state["steps"].get(step.name, {}).get("status") == "completed":
                raise FileExistsError(f"Stage already completed: {step.name}")
            for path in step.outputs:
                if Path(path).exists():
                    raise FileExistsError(f"Refusing to overwrite stage output: {path}")
            env = os.environ.copy()
            env.update({"OMP_NUM_THREADS": str(args.threads), "OPENBLAS_NUM_THREADS": str(args.threads)})
            if args.gpu is not None:
                env["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
            env.update({k: str(v) for k, v in step.env.items()})
            command = list(map(str, step.command))
            print(shlex.join(command), flush=True)
            start = time.monotonic()
            state["steps"][step.name] = {"status": "running", "command": command}
            save()
            with (root / "logs" / (step.name + ".log")).open("x") as log:
                subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            missing = [str(p) for p in step.outputs if not Path(p).exists()]
            if missing:
                raise RuntimeError(f"Stage returned without required outputs: {missing}")
            state["steps"][step.name].update(status="completed", seconds=time.monotonic() - start)
            save()
        state["status"] = "completed" if all(state["steps"].get(s.name, {}).get("status") == "completed" for s in steps) else "stages_completed"
    except BaseException as error:
        state.update(status="failed", error=str(error))
        raise
    finally:
        save()
    print(manifest)
