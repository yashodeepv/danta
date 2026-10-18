"""web.py - Spec Studio's API inside the browser (GitHub Pages, through Pyodide).

The page in site/ runs this module in Pyodide and answers its own /api/ requests
with it: the same answers `danta studio` gives, except that running a project's
tests needs Node, Maven and a JDK, so the browser asks the user to run them.
Everything crosses the JavaScript boundary as JSON text or bytes.
"""

import json

import os

from danta.app.pipeline import build, project_zip
from danta.app.prompt import build_prompt, examples
from danta.gen.correct import build_correction_prompt
from danta.design.context import extract as extract_design_context, format_for_prompt as format_design_context
from danta.design.parser import parse_design
from danta.design.validate import validate as validate_design
from danta.design.codegen import generate as design_generate
from danta.spec import compile_spec

RUN_LOCALLY = {
    'python': 'pip install -e . && python -m unittest discover -s tests -t .',
    'javascript': 'npm install && npm test',
    'java': 'mvn test',
}


def api_prompt():
    return build_prompt()


def api_examples():
    return json.dumps(examples())


def api_build(spec):
    return json.dumps(build(spec))


def api_project(spec, language, design_spec=''):
    """The project zip as bytes, or None when the spec doesn't build cleanly."""
    design_html = None
    if design_spec and design_spec.strip():
        res = compile_spec(spec) if spec and spec.strip() else None
        ctx = extract_design_context(res) if (res and not res.errors) else {}
        dspec = parse_design(design_spec)
        if not dspec.errors:
            if ctx:
                validate_design(dspec, ctx)
            if not dspec.errors:
                design_html = design_generate(dspec, ctx)
    data, _ = project_zip(spec, language, design_html=design_html)
    return data


def api_verify(language):
    return json.dumps({'status': 'local', 'passed': 0, 'total': 0, 'command': RUN_LOCALLY.get(language, ''),
                       'detail': 'tests run on your machine'})


def api_design_prompt(spec):
    res = compile_spec(spec)
    if res.errors:
        return json.dumps({'ok': False, 'error': f'{len(res.errors)} backend spec error(s) — fix those first'})
    ctx = extract_design_context(res)
    context_text = format_design_context(ctx)
    skill_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools', 'danta-design-skill.md')
    try:
        with open(skill_path) as f:
            skill = f.read()
    except OSError:
        skill = '(design skill file not found in Pyodide bundle)'
    prompt = skill.replace('{{system_context}}', context_text)
    return json.dumps({'ok': True, 'prompt': prompt, 'context': ctx})


def api_design_build(spec, design_spec):
    """Parse + validate + generate HTML preview from a design spec.
    spec may be empty; if present it's compiled to supply backend context."""
    ctx = {}
    if spec and spec.strip():
        res = compile_spec(spec)
        if not res.errors:
            ctx = extract_design_context(res)
    dspec = parse_design(design_spec or '')
    if dspec.errors:
        return json.dumps({'ok': False, 'errors': dspec.errors})
    if ctx:
        validate_design(dspec, ctx)
    if dspec.errors:
        return json.dumps({'ok': False, 'errors': dspec.errors})
    html = design_generate(dspec, ctx)
    return json.dumps({'ok': True, 'html': html})


def api_correction_prompt(spec, attempt=1, max_attempts=3, user_note=''):
    result = build(spec)
    errors = result.get('errors', [])
    if not errors:
        return json.dumps({'prompt': '', 'has_errors': False})
    prompt = build_correction_prompt(errors=errors, spec=spec, attempt=int(attempt), max_attempts=int(max_attempts), user_note=str(user_note))
    return json.dumps({'prompt': prompt, 'has_errors': True, 'error_count': len(errors)})
