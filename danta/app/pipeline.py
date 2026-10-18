"""pipeline.py - What the Build button does: spec text -> everything the UI shows.

    spec text (as pasted, code fences and chatter allowed)
      -> compile (danta/spec)          errors with lines, or IR2 flows
      -> test runs (danta/gen/coverage) invented inputs until every edge is taken
      -> projects (danta/codegen)      Python, JavaScript and Spring Boot, each formatted
      -> verify (on request)          each project's own test suite, in its own language
"""

import dataclasses
import hashlib
import random
import re
from collections import OrderedDict

from danta.codegen.format import format_project
from danta.codegen.project import System, generate, verify_project
from danta.gen.coverage import synthesize
from danta.gen.order import canonical_order
from danta.ir2 import graph as g
from danta.ir2.expr import ArrLoop, Cmp, Const, Invalid, Pluck, Ref, Str, children
from danta.ir2.io import dump_flow
from danta.ir2.sexpr import emit
from danta.sim import run, summary
from danta.sim.runner import SimError
from danta.spec import compile_spec


def strip_fences(text):
    """Keep only the spec from an LLM reply: the fenced block if there is one,
    otherwise everything from the "Spec:" line on."""
    m = re.search(r'```[a-zA-Z]*\n(.*?)```', text, re.S)
    if m and 'Spec:' in m.group(1):
        text = m.group(1)
    i = text.find('Spec:')
    return text[i:] if i > 0 and text[:i].strip() else text


class FlowHints:
    """Value pools for inventing test inputs, read off the flow itself: a field
    compared with "gold" gets "gold" as a candidate, a field compared with
    100000 gets a range around it, so both sides of each test happen."""

    name = 'spec'

    def __init__(self, flow):
        self.ints, self.strings = {}, {}
        for e in _expressions(flow):
            stack = [e]
            while stack:
                n = stack.pop()
                stack.extend(children(n))
                if isinstance(n, Cmp):
                    for x, y in ((n.a, n.b), (n.b, n.a)):
                        f = _field(x)
                        if f and isinstance(y, Const):
                            self.ints.setdefault(f, set()).add(y.v)
                        if f and isinstance(y, Str):
                            self.strings.setdefault(f, set()).add(y.v)
                if isinstance(n, ArrLoop) and n.pred and isinstance(n.arr, Pluck) and n.pred[0] in ('gt', 'lt'):
                    self.ints.setdefault(n.arr.field, set()).add(n.pred[1])
        self.strings = {k: sorted(v) + ['other'] for k, v in self.strings.items()}

    def int_range(self, field):
        ks = self.ints.get(field)
        if not ks:
            return (0, 1000)
        return (min(0, min(ks) - 10), max(ks) * 2 + 10)

    def string_pool(self, field):
        return self.strings.get(field, ['alpha', 'beta'])


def _field(e):
    if isinstance(e, Ref):
        return e.path[-1]
    if isinstance(e, ArrLoop) and isinstance(e.arr, Pluck):
        return e.arr.field
    return None


def _expressions(flow):
    for s in flow.steps:
        if isinstance(s, g.Compute):
            yield from (e for _, e in s.assign)
        for attr in ('rule', 'cond', 'to', 'message'):
            if hasattr(s, attr):
                yield getattr(s, attr)
        for attr in ('args', 'data', 'response'):
            yield from (getattr(s, attr, None) or {}).values()


def _label(s):
    if s.title:
        return s.title
    if isinstance(s, g.Trigger):
        return {'http': f"{s.config.get('method')} {s.config.get('path')}", 'event': s.config.get('name'),
                'topic': f"topic {s.config.get('name')}", 'schedule': s.config.get('cron')}.get(s.source, s.source)
    if isinstance(s, g.Call):
        return f'{s.service}.{s.op}'
    if isinstance(s, g.Compute):
        return ', '.join(n for n, _ in s.assign)
    if isinstance(s, g.Persist):
        return f'{s.op} {s.entity}'
    if isinstance(s, g.Notify):
        return s.channel
    if isinstance(s, g.Query):
        return f'find {s.entity} records'
    if isinstance(s, g.Publish):
        return f'publish {"each " if s.each is not None else ""}to {s.topic}'
    if isinstance(s, g.End):
        return 'stop' if s.status == 'ok' else 'error'
    return s.kind


def _sub(s):
    if isinstance(s, g.Call):
        return f'call · {s.service}.{s.op}' + (f' · retries {s.retries}' if s.retries else '')
    if isinstance(s, g.Trigger):
        return f'trigger · {s.source}'
    if isinstance(s, g.End):
        return f'end · {s.status}'
    if isinstance(s, g.Persist):
        return f'{s.op} · {s.entity}'
    if isinstance(s, g.Notify):
        return f'notify · {s.channel}'
    if isinstance(s, g.Query):
        return f'query · {s.entity}'
    if isinstance(s, g.Publish):
        return f'publish · {s.topic}'
    return {'branch': 'if'}.get(s.kind, s.kind)


def _logic(s):
    pairs = []
    if isinstance(s, g.Validate):
        pairs = [('rule', s.rule)]
    elif isinstance(s, g.Branch):
        pairs = [('cond', s.cond)]
    elif isinstance(s, g.Compute):
        pairs = list(s.assign)
    elif isinstance(s, g.Call):
        pairs = list(s.args.items())
    elif isinstance(s, g.Persist):
        pairs = list(s.data.items())
    elif isinstance(s, g.Notify):
        pairs = [('to', s.to), ('message', s.message)]
    elif isinstance(s, g.Query):
        pairs = list(s.where.items())
    elif isinstance(s, g.Publish):
        pairs = [('each', s.each)] if s.each is not None else list(s.message.items())
    elif isinstance(s, g.End) and s.response:
        pairs = list(s.response.items())
    out = []
    for k, e in pairs:
        out.append([k, f'(needs the logic model) {e.text}' if isinstance(e, Invalid) else emit(e)])
    return out


def build(text, seed=0):
    spec = strip_fences(text)
    res = compile_spec(spec)
    out = {
        'ok': res.ok, 'system': res.system, 'description': res.description, 'spec': spec,
        'errors': [{'line': e.line, 'rule': e.rule, 'message': e.message} for e in res.errors],
        'warnings': [{'line': e.line, 'rule': e.rule, 'message': e.message} for e in res.warnings],
        'intents': [{'line': i.line, 'flow': i.flow, 'step': i.step, 'field': i.field, 'text': i.text}
                    for i in res.intents],
        'flows': [],
    }
    rng = random.Random(seed)
    all_scenarios = {}
    for flow in res.flows:
        item = {
            'name': flow.name, 'mode': flow.mode, 'intent': flow.intent,
            'order': canonical_order(flow),
            'steps': [{'id': s.id, 'kind': s.kind, 'label': _label(s), 'sub': _sub(s),
                       'status': getattr(s, 'status', None), 'line': res.lines.get((flow.name, s.id), 0),
                       'logic': _logic(s)} for s in flow.steps],
            'edges': [{'src': e.src, 'dst': e.dst, 'on': e.on} for e in flow.edges],
            'ir2': dump_flow(flow),
            'runs': [], 'coverage': None,
        }
        pending = [i for i in res.intents if i.flow == flow.name]
        if res.errors:
            item['blocked'] = 'Fix the errors to generate test runs and code.'
        elif pending:
            item['blocked'] = (f'{len(pending)} value(s) are written as intent (prose), which needs the '
                               'logic model. Write them as exact expressions in backquotes to build code now.')
        else:
            scenarios, cov = synthesize(rng, flow, FlowHints(flow))
            all_scenarios[flow.name] = scenarios
            item['coverage'] = cov
            for name, sc in scenarios.items():
                try:
                    r = run(flow, sc['input'], sc.get('mocks', {}))
                    item['runs'].append({'name': name, 'input': sc['input'], 'mocks': sc.get('mocks', {}),
                                         'status': r.status, 'response': r.response, 'error': r.error,
                                         'path': r.path(), 'edges': [list(e) for e in r.edges],
                                         'effects': [summary(e) for e in r.effects]})
                except SimError as e:
                    item['runs'].append({'name': name, 'input': sc['input'], 'mocks': sc.get('mocks', {}),
                                         'status': 'skipped', 'response': {}, 'error': str(e),
                                         'path': [], 'edges': [], 'effects': []})
        out['flows'].append(item)
    out['screens'] = [dataclasses.asdict(s) for s in res.screens]
    out['project'] = {}
    if res.flows and len(all_scenarios) == len(res.flows):
        system = System(res.system, res.description, res.flows, all_scenarios, res.screens)
        for lang in LANGUAGES:
            files, fmt = format_project(generate(system, lang), lang)
            _remember(spec, lang, files)
            out['project'][lang] = {'files': files, 'format': fmt, 'verification': None}
    return out


LANGUAGES = ('python', 'javascript', 'java')

# The last few generated projects, so verifying or downloading one doesn't
# regenerate and reformat it. Generation is deterministic, so a miss is only slower.
_CACHE = OrderedDict()


def _key(spec, lang):
    return hashlib.sha256(spec.encode()).hexdigest(), lang


def _remember(spec, lang, files):
    _CACHE[_key(spec, lang)] = files
    while len(_CACHE) > 12:
        _CACHE.popitem(last=False)


def project_files(text, language, seed=0):
    """(files, system name) for a spec, or (None, name) if it doesn't build cleanly."""
    spec = strip_fences(text)
    files = _CACHE.get(_key(spec, language))
    if files is not None:
        return files, next(iter(files)).split('/')[0]
    result = build(text, seed)
    project = result.get('project', {}).get(language)
    return (project['files'] if project else None), result['system']


def verify_language(text, language):
    """Run the generated project's own test suite."""
    files, _ = project_files(text, language)
    if files is None:
        return {'status': 'not verified', 'passed': 0, 'total': 0, 'detail': 'build the spec without errors first'}
    return verify_project(files, language)


_DESIGN_NGINX = r'''# Serves the design HTML and forwards /api/* to the backend (strips /api prefix).
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;

  location /api/ {
    proxy_pass ${API_URL}/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }

  location / {
    try_files $uri $uri/ /index.html;
  }
}
'''

_DESIGN_DOCKERFILE = '''FROM nginx:1.27-alpine
# nginx substitutes ${API_URL} when the container starts
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY index.html /usr/share/nginx/html/
RUN chmod -R a+r /usr/share/nginx/html
ENV API_URL=http://app:__PORT__
EXPOSE 80
'''

_LANG_PORT = {'python': 8000, 'javascript': 3000, 'java': 8080}


def project_zip(text, language, seed=0, design_html=None):
    """The generated project as a zip, or None if the spec doesn't build cleanly.
    When design_html is provided:
    - If the backend has ## Screen: sections, their React app (web/) moves to admin/ (port 3001)
      and the design HTML becomes the storefront web/ (port 3000).
    - If there are no backend screens, the design HTML is added as web/ and a compose service
      is injected for it."""
    from danta.codegen.project import zip_bytes
    files, system = project_files(text, language, seed)
    if files is None:
        return None, system
    if design_html:
        files = dict(files)
        web_prefix = f'{system}/web/'
        api_port = _LANG_PORT.get(language, 8000)
        has_admin = any(k.startswith(web_prefix) for k in files)

        if has_admin:
            # Move React admin app web/ → admin/
            admin_prefix = f'{system}/admin/'
            files = {
                k.replace(web_prefix, admin_prefix, 1) if k.startswith(web_prefix) else k: v
                for k, v in files.items()
            }
            # Patch compose: rename web service → admin at 3001, add storefront web at 3000
            compose_key = f'{system}/docker-compose.yml'
            if compose_key in files:
                files[compose_key] = _patch_compose_for_design(
                    files[compose_key], api_port, has_admin=True)
        else:
            files = {k: v for k, v in files.items() if not k.startswith(web_prefix)}
            # Inject a web service into compose for the storefront
            compose_key = f'{system}/docker-compose.yml'
            if compose_key in files:
                files[compose_key] = _patch_compose_for_design(
                    files[compose_key], api_port, has_admin=False)

        files[f'{system}/web/index.html'] = design_html
        files[f'{system}/web/nginx.conf.template'] = _DESIGN_NGINX
        files[f'{system}/web/Dockerfile'] = _DESIGN_DOCKERFILE.replace('__PORT__', str(api_port))
    return zip_bytes(files), system


_WEB_SERVICE_BLOCK = '''\
  web:
    build: ./web
    restart: unless-stopped
    ports:
      - "3000:80"
    environment:
      API_URL: "http://app:{port}"
    depends_on:
      app:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1/"]
      interval: 5s
      retries: 30'''


def _patch_compose_for_design(compose_text, api_port, has_admin):
    """Patch a docker-compose.yml for a design-spec build.

    has_admin=True:  rename the existing `web` service → `admin` at port 3001,
                     then append a new `web` service for the storefront at 3000.
    has_admin=False: append a new `web` service for the storefront at 3000.
    """
    web_block = _WEB_SERVICE_BLOCK.format(port=api_port)
    c = compose_text

    if has_admin:
        # Rename existing web service header and port
        c = c.replace(
            '  web:\n    build: ./web\n    restart: unless-stopped\n    ports:\n      - "3000:80"',
            '  admin:\n    build: ./admin\n    restart: unless-stopped\n    ports:\n      - "3001:80"',
        )
        # Update comment line
        c = c.replace(
            '#   Web app: http://localhost:3000',
            '#   Storefront: http://localhost:3000\n#   Admin panel: http://localhost:3001',
        )
    else:
        # Insert storefront comment after the API/docs comment line
        c = c.replace(
            f'#   API and Swagger UI: http://localhost:{api_port}/docs',
            f'#   API and Swagger UI: http://localhost:{api_port}/docs\n#   Storefront: http://localhost:3000',
        )

    # Append the storefront web service
    if '\nvolumes:' in c:
        c = c.replace('\nvolumes:', f'\n{web_block}\n\nvolumes:')
    else:
        c = c.rstrip() + f'\n{web_block}\n'
    return c
