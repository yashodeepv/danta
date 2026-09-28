"""web.py - Spec Studio's API inside the browser (GitHub Pages, through Pyodide).

The page in site/ runs this module in Pyodide and answers its own /api/ requests
with it: the same answers `danta studio` gives, except that running a project's
tests needs Node, Maven and a JDK, so the browser asks the user to run them.
Everything crosses the JavaScript boundary as JSON text or bytes.
"""

import json

from danta.app.pipeline import build, project_zip
from danta.app.prompt import build_prompt, examples

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


def api_project(spec, language):
    """The project zip as bytes, or None when the spec doesn't build cleanly."""
    data, _ = project_zip(spec, language)
    return data


def api_verify(language):
    return json.dumps({'status': 'local', 'passed': 0, 'total': 0, 'command': RUN_LOCALLY.get(language, ''),
                       'detail': 'tests run on your machine'})
