"""toolchain.py - The environments generated projects are verified in.

Generated projects depend on real frameworks now (FastAPI, Express, Spring
Boot, database and broker clients), so verification needs them installed:

    python   one cached virtualenv with the generated projects' dependencies,
             created on first use under ~/.cache/danta/
    node     `npm install` inside the project being verified (npm caches
             downloads, so only the first run is slow)
    java     Maven resolves the pom's dependencies into ~/.m2

The first verification on a new machine needs network access.
"""

import os
import shutil
import subprocess
import sys

CACHE = os.path.join(os.path.expanduser('~'), '.cache', 'danta')

# What every generated Python project may import. Kept in step with python_project.DEPENDENCIES.
PYTHON_PACKAGES = ['fastapi>=0.110', 'uvicorn>=0.29', 'httpx>=0.27', 'pymongo>=4.6', 'pika>=1.3']

_python = None


def python_env():
    """The interpreter of the verification virtualenv, creating it once. None if that fails."""
    global _python
    if _python:
        return _python
    root = os.path.join(CACHE, 'pyenv')
    py = os.path.join(root, 'bin', 'python')
    marker = os.path.join(root, '.packages')
    want = '\n'.join(PYTHON_PACKAGES)
    try:
        if not os.path.exists(py):
            subprocess.run([sys.executable, '-m', 'venv', root], check=True, capture_output=True, timeout=300)
        have = ''
        if os.path.exists(marker):
            with open(marker) as f:
                have = f.read()
        if have != want:
            subprocess.run([py, '-m', 'pip', 'install', '-q', '--disable-pip-version-check', *PYTHON_PACKAGES],
                           check=True, capture_output=True, timeout=900)
            with open(marker, 'w') as f:
                f.write(want)
    except (subprocess.SubprocessError, OSError):
        return None
    _python = py
    return py


def npm_install(root, timeout=900):
    """Install a Node project's dependencies. Returns (ok, output)."""
    npm = shutil.which('npm')
    if npm is None:
        return False, 'npm is not installed'
    p = subprocess.run([npm, 'install', '--no-audit', '--no-fund', '--prefer-offline', '--loglevel=error'],
                       cwd=root, capture_output=True, text=True, timeout=timeout)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def web_modules(package_json, timeout=900):
    """node_modules for a generated web app, installed once per distinct package.json under
    ~/.cache/danta/web/ (React, Vite and vitest are too big to install per check).
    Returns (path or None, output)."""
    import hashlib
    npm = shutil.which('npm')
    if npm is None:
        return None, 'npm is not installed'
    root = os.path.join(CACHE, 'web', hashlib.sha256(package_json.encode()).hexdigest()[:16])
    modules = os.path.join(root, 'node_modules')
    if os.path.exists(os.path.join(root, '.installed')):
        return modules, ''
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, 'package.json'), 'w') as f:
        f.write(package_json)
    p = subprocess.run([npm, 'install', '--no-audit', '--no-fund', '--prefer-offline', '--loglevel=error'],
                       cwd=root, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        return None, (p.stdout + p.stderr).strip()
    open(os.path.join(root, '.installed'), 'w').close()
    return modules, ''
