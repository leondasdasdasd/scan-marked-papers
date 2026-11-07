"""Reuse existing task-local Python environments without installing dependencies."""
import os
from pathlib import Path
import sys


def python_candidates():
    values=[]
    if os.environ.get('PAPERFLOW_PYTHON'):values.append(Path(os.environ['PAPERFLOW_PYTHON']).expanduser())
    if os.environ.get('VIRTUAL_ENV'):values.append(Path(os.environ['VIRTUAL_ENV'])/'bin/python')
    for parent in (Path.cwd(),*Path.cwd().parents):
        for name in ('.venv','venv'):values.append(parent/name/'bin/python')
    seen={str(Path(sys.executable).absolute())}
    for value in values:
        # Keep the venv symlink path: resolving it would discard the environment.
        key=str(value.absolute())
        if key not in seen and value.is_file() and os.access(value,os.X_OK):
            seen.add(key);yield value
