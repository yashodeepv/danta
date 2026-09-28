"""format.py - Run each language's standard formatter over a generated project.

    python      ruff format          (black-compatible)
    javascript  prettier
    java        google-java-format
    web/        prettier, whichever the backend (the React app is the same for all)

Formatting happens before verification, so the files a user downloads are
the files that were tested. A formatter that isn't installed leaves the
project as generated and says so; it never blocks a build.
"""

import os
import shutil
import subprocess
import tempfile

from danta.codegen.project import write

TOOLS = {
    'python': 'ruff',
    'javascript': 'prettier',
    'java': 'google-java-format',
}
EXTENSIONS = {'python': ('.py',), 'javascript': ('.js', '.mjs', '.json'), 'java': ('.java',)}
WEB = ('.js', '.jsx', '.json', '.css')


def _command(language, root, paths):
    if language == 'python':
        return ['ruff', 'format', '--quiet', '--line-length', '100', '.']
    if language == 'javascript':
        return ['prettier', '--write', '--log-level', 'warn', '--print-width', '100', '--single-quote', *paths]
    return ['google-java-format', '--replace', *paths]


def _web(path):
    return '/web/' in path


def format_project(files, language):
    """Returns (files, {'status': 'formatted' | 'not formatted', 'tool', 'detail'})."""
    files, rep = _format(files, language, [p for p in files if p.endswith(EXTENSIONS[language]) and not _web(p)])
    web = [p for p in files if _web(p) and p.endswith(WEB)]
    if web and rep['status'] == 'formatted':
        files, web_rep = _format(files, 'javascript', web)
        if web_rep['status'] != 'formatted' and shutil.which(TOOLS['javascript']):
            rep = {**web_rep, 'detail': 'web/: ' + web_rep['detail']}
    return files, rep


def indent_java(text, unit='  '):
    """Indent generated Java by brace depth: the fallback when google-java-format isn't
    installed (and in the browser, where it can't be). Strings, chars and comments don't count."""
    out, depth, in_block = [], 0, False
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            out.append('')
            continue
        if in_block:
            out.append(unit * depth + ' ' + line)
            in_block = '*/' not in line
            continue
        opens = closes = 0
        lead = True                      # closing braces before any other code dedent this line
        dedent = 0
        i, quote = 0, None
        while i < len(line):
            c = line[i]
            if quote:
                if c == '\\':
                    i += 1
                elif c == quote:
                    quote = None
            elif c in '"\'':
                quote, lead = c, False
            elif line.startswith('//', i):
                break
            elif line.startswith('/*', i):
                end = line.find('*/', i + 2)
                if end < 0:
                    in_block = True
                    break
                i = end + 1
            elif c in '{(':
                opens += c == '{'
                lead = False
            elif c in '})':
                if c == '}':
                    closes += 1
                    dedent += lead
            elif not c.isspace():
                lead = False
            i += 1
        out.append(unit * max(depth - dedent, 0) + line)
        depth = max(depth + opens - closes, 0)
    return '\n'.join(out)


def _format(files, language, targets):
    tool = TOOLS[language]
    if shutil.which(tool) is None:
        if language == 'java' and targets:
            out = dict(files)
            for path in targets:
                out[path] = indent_java(files[path])
            return out, {'status': 'formatted', 'tool': 'the built-in indenter',
                         'detail': 'google-java-format is not installed; indented only'}
        return files, {'status': 'not formatted', 'tool': tool, 'detail': f'{tool} is not installed'}
    if not targets:
        return files, {'status': 'formatted', 'tool': tool, 'detail': ''}
    with tempfile.TemporaryDirectory() as d:
        write(files, d)
        p = subprocess.run(_command(language, d, targets), cwd=d, capture_output=True, text=True, timeout=180)
        if p.returncode != 0:
            return files, {'status': 'not formatted', 'tool': tool,
                           'detail': (p.stderr or p.stdout).strip()[-2000:]}
        out = {}
        for path in files:
            with open(os.path.join(d, path)) as f:
                out[path] = f.read()
    return out, {'status': 'formatted', 'tool': tool, 'detail': ''}
