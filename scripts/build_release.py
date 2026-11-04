#!/usr/bin/env python3
"""Build the runtime manifest and distribution ZIP without authentication or data."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import skill_update


def build(root):
    files = [root / 'SKILL.md', root / 'README.md']
    for name in ('agents', 'references', 'scripts'):
        files.extend(p for p in (root / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo'))
    manifest = {'schema_version': 1, 'repository': skill_update.REPOSITORY,
                'version': skill_update.current_version(root), 'files': {}}
    for path in sorted(files):
        relative = skill_update.safe_path(path.relative_to(root).as_posix())
        if path.is_symlink():
            raise ValueError('release_symlink')
        manifest['files'][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    skill_update.validate_manifest(manifest)
    manifest_path = root / skill_update.MANIFEST
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    archive = root / 'scan-marked-papers.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for path in [*sorted(files), manifest_path]:
            entry = zipfile.ZipInfo('scan-marked-papers/' + path.relative_to(root).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            package.writestr(entry, path.read_bytes())
    return {'version': manifest['version'], 'files': len(files) + 1,
            'zip': str(archive), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}


if __name__ == '__main__':
    print(json.dumps(build(Path(__file__).resolve().parents[1])))
