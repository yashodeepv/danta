"""server.py - A local HTTP server for Spec Studio. Standard library only.

    GET  /               the app (static/index.html)
    GET  /api/prompt     the LLM prompt, as text
    GET  /api/examples   the example specs
    POST /api/build      {"spec": "..."} -> everything the UI shows (pipeline.build)

Binds to 127.0.0.1 only: it runs code generation and simulation on
whatever is pasted in, and is meant for the person at this machine.
"""

import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from danta.app.pipeline import build, project_zip, verify_language
from danta.app.prompt import build_prompt, examples
from danta.gen.correct import build_correction_prompt
from danta.design.context import extract as extract_design_context, format_for_prompt as format_design_context
from danta.design.parser import parse_design
from danta.design.validate import validate as validate_design
from danta.design.codegen import generate as design_generate

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
MAX_BODY = 1_000_000



class Handler(BaseHTTPRequestHandler):
    server_version = 'SpecStudio/0.1'

    def log_message(self, fmt, *args):
        pass                                    # keep the terminal quiet

    def send(self, code, body, ctype):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj), 'application/json')

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            with open(os.path.join(STATIC, 'index.html'), 'rb') as f:
                self.send(200, f.read(), 'text/html; charset=utf-8')
        elif self.path == '/studio.html':
            with open(os.path.join(STATIC, 'studio.html'), 'rb') as f:
                self.send(200, f.read(), 'text/html; charset=utf-8')
        elif self.path in ('/danta-skill.md', '/danta-design-skill.md'):
            skill_file = os.path.join(os.path.dirname(os.path.dirname(STATIC)), '..', 'tools', self.path[1:])
            try:
                with open(os.path.normpath(skill_file), 'rb') as f:
                    self.send(200, f.read(), 'text/markdown; charset=utf-8')
            except OSError:
                self.send(404, 'not found', 'text/plain')
        elif self.path == '/api/prompt':
            self.send(200, build_prompt(), 'text/plain; charset=utf-8')
        elif self.path == '/api/examples':
            self.json(examples())
        else:
            self.send(404, 'not found', 'text/plain')

    def do_POST(self):
        if self.path not in ('/api/build', '/api/project', '/api/verify', '/api/correction-prompt', '/api/design-prompt', '/api/design-build'):
            return self.send(404, 'not found', 'text/plain')
        n = int(self.headers.get('Content-Length', 0))
        if n > MAX_BODY:
            return self.json({'fatal': 'the spec is too large (limit 1 MB)'}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b'{}')
            spec = body.get('spec', '')
            if self.path == '/api/verify':
                return self.json(verify_language(spec, body.get('language', 'python')))
            if self.path == '/api/project':
                lang = body.get('language', 'python')
                design_html = None
                design_spec_text = body.get('design_spec', '')
                if design_spec_text and design_spec_text.strip():
                    from danta.spec import compile_spec
                    res = compile_spec(spec) if spec.strip() else None
                    ctx = extract_design_context(res) if (res and not res.errors) else {}
                    dspec = parse_design(design_spec_text)
                    if not dspec.errors:
                        if ctx:
                            validate_design(dspec, ctx)
                        if not dspec.errors:
                            design_html = design_generate(dspec, ctx)
                data, system = project_zip(spec, lang, design_html=design_html)
                if data is None:
                    return self.json({'fatal': 'build the spec without errors first'}, 400)
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', f'attachment; filename="{system}-{lang}.zip"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if self.path == '/api/correction-prompt':
                result = build(spec)
                errors = result.get('errors', [])
                if not errors:
                    return self.json({'prompt': '', 'has_errors': False})
                attempt = int(body.get('attempt', 1))
                max_attempts = int(body.get('max_attempts', 3))
                user_note = str(body.get('user_note', ''))
                prompt = build_correction_prompt(spec, errors, attempt=attempt, max_attempts=max_attempts, user_note=user_note)
                return self.json({'prompt': prompt, 'has_errors': True, 'error_count': len(errors)})
            if self.path == '/api/design-prompt':
                from danta.spec import compile_spec
                import os
                res = compile_spec(spec)
                if res.errors:
                    return self.json({'ok': False, 'error': f'{len(res.errors)} backend spec error(s) — fix those first'})
                ctx = extract_design_context(res)
                context_text = format_design_context(ctx)
                skill_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          '..', 'tools', 'danta-design-skill.md')
                try:
                    with open(skill_path) as f:
                        skill = f.read()
                except OSError:
                    skill = '(design skill file not found)'
                prompt = skill.replace('{{system_context}}', context_text)
                return self.json({'ok': True, 'prompt': prompt, 'context': ctx})
            if self.path == '/api/design-build':
                from danta.spec import compile_spec
                design_spec_text = body.get('design_spec', '')
                if not design_spec_text.strip():
                    return self.json({'ok': False, 'errors': ['No design spec provided']})
                res = compile_spec(spec) if spec.strip() else None
                ctx = extract_design_context(res) if (res and not res.errors) else {}
                dspec = parse_design(design_spec_text)
                if dspec.errors:
                    return self.json({'ok': False, 'errors': dspec.errors})
                if ctx:
                    validate_design(dspec, ctx)
                if dspec.errors:
                    return self.json({'ok': False, 'errors': dspec.errors})
                html = design_generate(dspec, ctx)
                return self.json({'ok': True, 'html': html})
            self.json(build(spec))
        except Exception as e:                  # a bug here should show in the UI, not kill the server
            traceback.print_exc()
            self.json({'fatal': f'{type(e).__name__}: {e}'}, 500)


def serve(port=8765, open_browser=True):
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{port}/'
    print(f'Spec Studio running at {url}  (Ctrl+C to stop)')
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
