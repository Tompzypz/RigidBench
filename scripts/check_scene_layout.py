"""Static check of the scripts/ scene layout, without running solvers or Blender.

Verifies, for every scene in scene_registry.json:
  * the canonical files exist (three entries, README, entrypoints, scene_config,
    edit_vocab, requirements, scene_manifest);
  * every Python file parses and carries the unified-entry preamble;
  * entrypoints.json names match the on-disk files;
  * declared implementation files, module homes and assets exist.

This is a read-only structural check. It does NOT run ``--help``/``--dry-run``
because the entries need the PyBullet/Blender environments.
"""
from pathlib import Path
import argparse
import ast
import json

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                              # repository root

REQUIRED_FILES = ('README.md', 'entrypoints.json', 'edit_vocab.py', 'scene_config.py',
                  'requirements.txt', 'scene_manifest.json')
ROLES = ('simulate', 'render', 'build_pcve')
MARKER = '# PCVE_UNIFIED_ENTRY_BEGIN'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json', type=Path, help='Write a full JSON report to this path')
    p.add_argument('--skip-assets', action='store_true', help='Do not require the referenced assets to exist')
    a = p.parse_args()

    registry = json.loads((HERE / 'scene_registry.json').read_text(encoding='utf-8'))['scenes']
    errors = []
    checked = 0

    for row in registry:
        scene = row['scene']
        folder = ROOT / row['directory']

        if not folder.is_dir():
            errors.append(str(folder))
            continue

        for name in REQUIRED_FILES:
            if not (folder / name).is_file():
                errors.append(str(folder / name))

        for role in ROLES:
            path = folder / f'{role}_{scene}.py'
            if not path.is_file():
                errors.append(str(path))
                continue
            checked += 1
            text = path.read_text(encoding='utf-8')
            try:
                ast.parse(text, filename=str(path))
            except SyntaxError as exc:
                errors.append(f'{path}: {exc}')
            if MARKER not in text:
                errors.append(f'{path}: missing {MARKER}')

        for path in folder.rglob('*.py'):
            try:
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            except SyntaxError as exc:
                errors.append(f'{path}: {exc}')

        metadata_path = folder / 'entrypoints.json'
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError as exc:
                errors.append(f'{metadata_path}: {exc}')
                continue
            for role in ROLES:
                expected = metadata.get('entrypoints', {}).get(role, {}).get('file')
                if expected != f'{role}_{scene}.py':
                    errors.append(f'{folder}: {role} declares {expected!r}')
                elif not (folder / expected).is_file():
                    errors.append(f'{folder}: {role} points to missing {expected}')
            for workflow, spec in metadata.get('workflows', {}).items():
                if not (folder / spec['file']).is_file():
                    errors.append(f'{folder}: workflow {workflow} points to missing {spec["file"]}')
            for impl in metadata.get('implementation_files', []):
                if not (folder / impl).is_file():
                    errors.append(f'{folder}: implementation file missing {impl}')

        manifest_path = folder / 'scene_manifest.json'
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError as exc:
                errors.append(f'{manifest_path}: {exc}')
                continue
            for name in manifest.get('files', []):
                if not (folder / name).is_file():
                    errors.append(f'{manifest_path}: lists missing {name}')
            if not a.skip_assets:
                assets = manifest.get('assets', {})
                for name in assets.get('models', []):
                    if not (ROOT / 'assets' / 'models' / name).is_file():
                        errors.append(f'{scene}: missing asset models/{name}')
                for name in assets.get('texture_sets', []):
                    if not (ROOT / 'assets' / 'polyhaven' / name).is_dir():
                        errors.append(f'{scene}: missing asset polyhaven/{name}')
                for name in assets.get('scenarios', []):
                    if not (ROOT / 'assets' / 'scenarios' / name).is_dir():
                        errors.append(f'{scene}: missing asset scenarios/{name}')

    report = {
        'passed': not errors,
        'scenes': len(registry),
        'checked_entries': checked,
        'errors': errors,
        'scope': 'Static structural check only; solvers and renderers are not executed.',
    }
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    print(json.dumps({k: report[k] for k in ('passed', 'scenes', 'checked_entries', 'errors')},
                     indent=2, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
