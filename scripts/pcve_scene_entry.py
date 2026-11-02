"""Uniform, read-only planning around scene-owned implementations.

No physical defaults live here. A normal invocation is translated into the
original scene arguments, then the original module continues in this process.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("all", "prepare", "simulate", "surface", "render", "verify", "edits")


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _arguments():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def _replace_arguments(values):
    prefix = sys.argv[:sys.argv.index("--") + 1] if "--" in sys.argv else sys.argv[:1]
    sys.argv[:] = prefix + values


def _take(values, flag, many=False):
    values = list(values)
    result = None
    indices = [i for i, token in enumerate(values) if token == flag or token.startswith(flag + "=")]
    if len(indices) > 1:
        raise ValueError("Repeated argument: " + flag)
    if indices:
        index = indices[0]
        token = values[index]
        if "=" in token:
            result = token.split("=", 1)[1]
            del values[index]
        elif many:
            end = index + 1
            while end < len(values) and not values[end].startswith("--"):
                end += 1
            result = values[index + 1:end]
            del values[index:end]
        else:
            if index + 1 == len(values):
                raise ValueError("Missing value for " + flag)
            result = values[index + 1]
            del values[index:index + 2]
    return values, result


def parser(scene, role, spec):
    p = argparse.ArgumentParser(
        description=f"{scene['category']}/{scene['scene']} — {role}",
        epilog="Scene-specific arguments are forwarded unchanged. Use --describe for the exact native interface.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    p.add_argument("--out-root", type=Path, help="Output root; native output aliases remain supported")
    p.add_argument("--dry-run", action="store_true", help="Print the execution plan without imports, writes or child processes")
    p.add_argument("--describe", action="store_true", help="Print entry points, native options and current workflows as JSON")
    p.add_argument("--python", type=Path, help="Python runtime override; otherwise retain the scene's runtime")
    p.add_argument("--blender", type=Path, help="Blender runtime override; otherwise retain the scene's runtime")
    p.add_argument("--gpu", help="GPU index/UUID; inherited when omitted")
    p.add_argument("--threads", type=positive, help="Thread override; native defaults are retained when omitted")
    if role == "build_pcve":
        p.add_argument("--workflow", choices=["main", *scene.get("workflows", {})], default="main")
        p.add_argument("--stage", help="Native stage selector when supported by the selected workflow")
        p.add_argument("--cases", nargs="*", help="Scene-native case IDs; see --list-cases")
        p.add_argument("--list-cases", action="store_true")
    native = spec.get("native_options", [])
    if native:
        p.epilog += "\nNative options: " + ", ".join(native)
    return p


def _command(path, role, spec, values, options):
    if spec.get("runtime") == "blender":
        blender = options.blender or Path.home() / ".local/opt/blender-4.3.2-linux-x64/blender"
        command = [str(blender), "-b"]
        if options.threads:
            command += ["-t", str(options.threads)]
        command += ["--python-exit-code", "1", "--python", str(path), "--", *values]
    else:
        python = options.python or spec.get("python_runtime") or sys.executable
        command = [str(python), str(path), *values]
    return command


def normalize(scene, role, spec, values, entry_path):
    """Return native arguments and explicit resource overrides, without effects."""
    values = list(values)
    # --stage was a Blender asset path in a few native builders. Keep that
    # spelling compatible; --input-blend is its unambiguous public alias.
    preserved_stage = None
    if role == "build_pcve" and spec.get("stage_semantics") == "asset":
        remaining, candidate = _take(values, "--stage")
        if candidate is not None and candidate not in STAGES:
            values, preserved_stage = remaining, candidate
        values, input_blend = _take(values, "--input-blend")
        if input_blend is not None:
            if preserved_stage is not None:
                raise ValueError("Use only one of --input-blend and the native --stage asset")
            preserved_stage = str(Path(input_blend).expanduser().resolve())
    p = parser(scene, role, spec)
    options, remainder = p.parse_known_args(values)
    if remainder and remainder[0] == "--":
        remainder = remainder[1:]
    if preserved_stage is not None:
        remainder += ["--stage", preserved_stage]
    if options.describe:
        return options, remainder, p
    # Keep scene-native --cases values in the original order.
    if role == "build_pcve" and options.cases is not None:
        if "--cases" not in spec.get("native_options", []):
            p.error("This workflow builds its original case set; --cases is not supported")
        remainder += ["--cases", *options.cases]
    if role == "build_pcve" and options.stage:
        if spec.get("stage_semantics") != "selector":
            if options.stage != "all":
                p.error("Use the simulate/render entry for this scene; this workflow owns the complete build")
        else:
            remainder += ["--stage", options.stage]
    if options.out_root is not None:
        output = spec.get("output")
        if not output:
            p.error("This native stage needs its documented input/cache directory; no output alias is declared")
        target = options.out_root.expanduser().resolve()
        if output.get("filename"):
            target /= output["filename"]
        if output.get("flag"):
            flag = output["flag"]
            remainder, existing = _take(remainder, flag)
            if existing is not None and Path(existing).expanduser().resolve() != target:
                p.error("Conflicting --out-root and " + flag)
            remainder += [flag, str(target)]
        else:
            index = output.get("position", 0)
            remainder.insert(index, str(target))
    for name in ("python", "blender", "gpu", "threads"):
        value = getattr(options, name)
        native_flag = spec.get("resource_flags", {}).get(name)
        if value is not None and native_flag:
            remainder += [native_flag, str(value)]
    return options, remainder, p


def prepare_entry(filename, role):
    """Called before any scene/Blender imports; normal execution stays native."""
    if getattr(sys, "_pcve_native_diagnostic", False):
        return
    path = Path(filename).resolve()
    manifest = path.parent / "entrypoints.json"
    scene = json.loads(manifest.read_text())
    values = _arguments()
    # Internal diagnostics retain their previous semantics, while public
    # --dry-run is uniformly read-only.
    if "--native-help" in values or "--native-dry-run" in values:
        sys._pcve_native_diagnostic = True
        _replace_arguments([{"--native-help": "--help", "--native-dry-run": "--dry-run"}.get(v, v) for v in values])
        return
    spec = scene["entrypoints"][role]
    workflow = "main"
    if role == "build_pcve":
        _, selected = _take(values, "--workflow")
        if selected and selected != "main":
            workflow = selected
            if workflow not in scene.get("workflows", {}):
                parser(scene, role, spec).error("Unknown workflow: " + workflow)
            spec = scene["workflows"][workflow]
    options, native, p = normalize(scene, role, spec, values, path)
    if options.describe:
        print(json.dumps(scene, indent=2, ensure_ascii=False))
        raise SystemExit(0)
    if role == "build_pcve" and options.list_cases:
        print(json.dumps({"scene": scene["scene"], "workflow": workflow,
                          "cases": spec.get("cases", []), "workflows": list(scene.get("workflows", {}))}, indent=2))
        raise SystemExit(0)
    target = path if workflow == "main" else path.parent / spec["file"]
    command = _command(target, role, spec, [*spec.get("prefix_args", []), *native], options)
    overrides = {}
    if options.gpu is not None:
        overrides["CUDA_VISIBLE_DEVICES"] = str(options.gpu)
    if options.threads is not None:
        overrides.update(OMP_NUM_THREADS=str(options.threads), OPENBLAS_NUM_THREADS=str(options.threads), MKL_NUM_THREADS=str(options.threads))
    if options.dry_run:
        print(json.dumps({"schema_version": 1, "scene": scene["scene"], "category": scene["category"],
             "entry": role, "workflow": workflow, "dry_run": True,
             "out_root": str(options.out_root.expanduser().resolve()) if options.out_root else None,
             "command": command, "env": overrides,
             "physics_policy": "Scene-native defaults and solver/render implementation are unchanged"}, indent=2))
        raise SystemExit(0)
    os.environ.update(overrides)
    if workflow != "main":
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(path.parent), str(ROOT / "scripts"), env.get("PYTHONPATH", "")])
        raise SystemExit(subprocess.run(command, cwd=ROOT, env=env).returncode)
    if spec.get("runtime") == "blender" and "bpy" not in sys.modules and not Path(sys.executable).name.lower().startswith("blender"):
        raise SystemExit(subprocess.run(command, cwd=ROOT).returncode)
    if spec.get("runtime") != "blender" and options.python and options.python.expanduser().resolve() != Path(sys.executable).resolve():
        raise SystemExit(subprocess.run(command, cwd=ROOT).returncode)
    if options.out_root is not None and spec.get("output", {}).get("filename"):
        options.out_root.expanduser().resolve().mkdir(parents=True, exist_ok=True)
    _replace_arguments(native)
