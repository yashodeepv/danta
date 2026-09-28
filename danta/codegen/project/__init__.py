"""project - A whole system -> a complete project, verified by its own tests.

    common.py              the system model, names, types
    python_project.py      Python package: flows, models, ports, triggers, adapters, tests
    javascript_project.py  Node.js project: the same, as ES modules with node:test

    files = generate(system, 'python')           # {relative path: content}
    report = verify_project(files, 'python')     # runs the generated test suite

A generated project is verified the way a person would check it: by
running its own test suite, in its own language, with its own test runner.
The tests are the simulator's scenarios, so passing them means the project
behaves exactly like the verified flows.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from danta.codegen.project import java_project, javascript_project, python_project
from danta.codegen.project.common import System

GENERATORS = {'python': python_project.generate, 'javascript': javascript_project.generate,
              'java': java_project.generate}


def generate(system, language):
    return GENERATORS[language](system)


def write(files, root):
    for path, content in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, content in sorted(files.items()):
            z.writestr(path, content)
    return buf.getvalue()


def verify_project(files, language, timeout=120):
    """{'status': 'verified' | 'failed' | 'not verified', 'passed', 'total', 'detail'}"""
    top = sorted({p.split('/')[0] for p in files})
    if len(top) != 1:
        raise ValueError('a project has exactly one top-level folder')
    with tempfile.TemporaryDirectory() as d:
        write(files, d)
        root = os.path.join(d, top[0])
        if language == 'python':
            from danta.codegen.toolchain import python_env
            py = python_env()
            if py is None:
                return {'status': 'not verified', 'passed': 0, 'total': 0,
                        'detail': 'could not create the Python environment (fastapi, uvicorn, httpx)'}
            env = {**os.environ, 'PYTHONPATH': os.path.join(root, 'src')}
            p = subprocess.run([py, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'],
                               cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
            text = p.stderr + p.stdout
            m = re.search(r'Ran (\d+) tests?', text)
            total = int(m.group(1)) if m else 0
            fails = sum(int(x) for x in re.findall(r'(?:failures|errors)=(\d+)', text))
            passed = total - fails if p.returncode == 0 or fails else 0
        elif language == 'java':
            mvn = shutil.which('mvn')
            if mvn is None:
                return {'status': 'not verified', 'passed': 0, 'total': 0, 'detail': 'Maven (mvn) is not installed'}
            p = subprocess.run([mvn, '-B', '-Dstyle.color=never', 'test'], cwd=root, capture_output=True,
                               text=True, timeout=max(timeout, 900))
            text = p.stdout + p.stderr
            runs = re.findall(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)(?!,)', text)
            total, fails = (int(runs[-1][0]), int(runs[-1][1]) + int(runs[-1][2])) if runs else (0, 0)
            passed = total - fails
            if p.returncode != 0 and not runs:
                text = '\n'.join(l for l in text.splitlines() if 'ERROR' in l or 'error:' in l) or text
        else:
            if shutil.which('node') is None:
                return {'status': 'not verified', 'passed': 0, 'total': 0, 'detail': 'Node.js is not installed'}
            from danta.codegen.toolchain import npm_install
            ok_install, out = npm_install(root)
            if not ok_install:
                return {'status': 'failed', 'passed': 0, 'total': 0, 'detail': 'npm install: ' + out[-3000:]}
            tests = sorted(os.path.join('test', f) for f in os.listdir(os.path.join(root, 'test'))
                           if f.endswith('.test.js'))
            p = subprocess.run(['node', '--test', '--test-reporter=tap', *tests], cwd=root,
                               capture_output=True, text=True, timeout=timeout)
            text = p.stdout + p.stderr
            pm, fm = re.search(r'# pass (\d+)', text), re.search(r'# fail (\d+)', text)
            passed, fails = int(pm.group(1)) if pm else 0, int(fm.group(1)) if fm else 0
            total = passed + fails
        ok = p.returncode == 0 and total > 0 and passed == total
        rep = {'status': 'verified' if ok else 'failed', 'passed': passed, 'total': total,
               'detail': '' if ok else text.strip()[-3000:]}
        web = os.path.join(root, 'web')
        if os.path.isdir(web):
            rep = _merge(rep, verify_web(web, timeout))
        return rep


def _merge(backend, web):
    if web['status'] == 'not verified':
        return {**backend, 'detail': (backend['detail'] + '\nweb/: ' + web['detail']).strip()}
    ok = backend['status'] == 'verified' and web['status'] == 'verified'
    detail = '\n'.join(d for d in (backend['detail'], web['detail'] and 'web/: ' + web['detail']) if d)
    return {'status': 'verified' if ok else 'failed', 'passed': backend['passed'] + web['passed'],
            'total': backend['total'] + web['total'], 'detail': detail}


def verify_web(web, timeout=120):
    """The React app's own tests (vitest), then a production build."""
    from danta.codegen.toolchain import web_modules
    if shutil.which('node') is None:
        return {'status': 'not verified', 'passed': 0, 'total': 0, 'detail': 'Node.js is not installed'}
    with open(os.path.join(web, 'package.json')) as f:
        modules, out = web_modules(f.read())
    if modules is None:
        return {'status': 'failed', 'passed': 0, 'total': 0, 'detail': 'npm install: ' + out[-3000:]}
    os.symlink(modules, os.path.join(web, 'node_modules'))
    bin_ = os.path.join(web, 'node_modules', '.bin')
    p = subprocess.run([os.path.join(bin_, 'vitest'), 'run', '--reporter=verbose'], cwd=web,
                       capture_output=True, text=True, timeout=max(timeout, 300), env={**os.environ, 'CI': '1'})
    text = re.sub(r'\x1b\[[0-9;]*m', '', p.stdout + p.stderr)
    m = re.search(r'Tests\s+(?:(\d+) failed \| )?(?:(\d+) passed )?\((\d+)\)', text)
    total = int(m.group(3)) if m else 0
    passed = int(m.group(2) or 0) if m else 0
    if p.returncode == 0 and total and passed == total:
        b = subprocess.run([os.path.join(bin_, 'vite'), 'build', '--logLevel', 'error'], cwd=web,
                           capture_output=True, text=True, timeout=max(timeout, 300))
        if b.returncode != 0:
            return {'status': 'failed', 'passed': passed, 'total': total,
                    'detail': 'vite build: ' + (b.stdout + b.stderr).strip()[-3000:]}
        return {'status': 'verified', 'passed': passed, 'total': total, 'detail': ''}
    return {'status': 'failed', 'passed': passed, 'total': total, 'detail': text.strip()[-3000:]}


__all__ = ['System', 'generate', 'verify_project', 'write', 'zip_bytes']
