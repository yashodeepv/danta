"""frontend.py - The system's screens -> a React (Vite) app in <project>/web.

The same app is generated for every backend: it only speaks HTTP, through
the endpoints the backends share (one per HTTP-triggered flow, and
GET /data/<entity> for list screens). In development Vite proxies /api to
the backend; in Docker and Kubernetes nginx serves the build and proxies
/api, so the browser only ever talks to one origin.

    web/src/ui.jsx               the widgets and layout, shared by every screen
    web/src/api.js               send(method, path, body), records(entity, filters)
    web/src/screens/<Name>.jsx   one component per `## Screen:`
    web/src/screens/<Name>.test.jsx   renders it, fills it in, checks what it sends
"""

import json
import random

from danta.codegen.project.common import camel
from danta.ui.model import label_of


def route(screen):
    return '/' + screen.name.replace('_', '-')


def js(v):
    return json.dumps(v, ensure_ascii=False)


def attr(v):
    """A JSX attribute value: "text" when that is safe, {"text"} otherwise."""
    return f'"{v}"' if not set(v) & set('"\\{}<>') else '{' + js(v) + '}'


def text(v):
    """JSX text content."""
    return v if not set(v) & set('{}<>') else '{' + js(v) + '}'


# ---------------------------------------------------------------- the widgets

UI = r'''// The building blocks every screen uses: layout, form widgets, the table and notices.
import { useId, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

export function Layout({ title, screens, children }) {
  return (
    <div className="app">
      <nav className="sidebar">
        <div className="brand">{title}</div>
        {screens.map((s) => (
          <NavLink key={s.path} to={s.path} className={({ isActive }) => (isActive ? 'active' : '')}>
            {s.title}
          </NavLink>
        ))}
      </nav>
      <main className="content">{children}</main>
    </div>
  );
}

/** A screen: its title, a notice passed by the screen that sent us here, then the body. */
export function Page({ title, notice, children }) {
  const flash = useLocation().state?.notice;
  return (
    <section className="page">
      <h1>{title}</h1>
      <Notice notice={notice || flash} />
      {children}
    </section>
  );
}

export function Notice({ notice }) {
  if (!notice) return null;
  return (
    <div className={`notice ${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
      {notice.text}
    </div>
  );
}

/** A label and its control. `bare` (inside a table row) keeps only the control, named by aria-label. */
function Field({ label, bare, children }) {
  const id = useId();
  if (bare) return children(id, label);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id)}
    </div>
  );
}

export function TextInput({ label, bare, value, onChange, type = 'text', readOnly = false }) {
  return (
    <Field label={label} bare={bare}>
      {(id, name) => (
        <input id={id} aria-label={name} type={type} value={value} readOnly={readOnly} required={!readOnly}
          onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}

export function LongText({ label, bare, value, onChange }) {
  return (
    <Field label={label} bare={bare}>
      {(id, name) => (
        <textarea id={id} aria-label={name} rows={4} value={value} required onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}

export function NumberInput({ label, bare, value, onChange }) {
  return (
    <Field label={label} bare={bare}>
      {(id, name) => (
        <input id={id} aria-label={name} type="number" step="1" value={value} required
          onChange={(e) => onChange(e.target.value === '' ? 0 : parseInt(e.target.value, 10))} />
      )}
    </Field>
  );
}

/** Money is stored in cents and typed in units: "12.50" is 1250. */
export function MoneyInput({ label, bare, value, onChange }) {
  const [text, setText] = useState(value ? (value / 100).toFixed(2) : '');
  return (
    <Field label={label} bare={bare}>
      {(id, name) => (
        <input id={id} aria-label={name} inputMode="decimal" placeholder="0.00" value={text} required
          pattern="[0-9]+([.][0-9]{1,2})?"
          onChange={(e) => {
            setText(e.target.value);
            onChange(Math.round((parseFloat(e.target.value) || 0) * 100));
          }} />
      )}
    </Field>
  );
}

export function Checkbox({ label, bare, value, onChange }) {
  return (
    <Field label={label} bare={bare}>
      {(id, name) => (
        <input id={id} aria-label={name} type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
      )}
    </Field>
  );
}

export function Choice({ label, bare, value, onChange, options }) {
  return (
    <Field label={label} bare={bare}>
      {(id, name) => (
        <select id={id} aria-label={name} value={options.indexOf(value)}
          onChange={(e) => onChange(options[Number(e.target.value)])}>
          {options.map((o, i) => (
            <option key={i} value={i}>{String(o)}</option>
          ))}
        </select>
      )}
    </Field>
  );
}

/** A list of words or numbers, typed separated by commas. */
export function ListInput({ label, bare, value, onChange, numbers = false }) {
  const [text, setText] = useState(value.join(', '));
  return (
    <Field label={label} bare={bare}>
      {(id, name) => (
        <input id={id} aria-label={name} value={text} placeholder="separate with commas"
          onChange={(e) => {
            setText(e.target.value);
            const items = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
            onChange(numbers ? items.map((s) => parseInt(s, 10)).filter((n) => !Number.isNaN(n)) : items);
          }} />
      )}
    </Field>
  );
}

/** A list of records, one table row each. columns: [{ name, label, blank, input(props) }] */
export function Rows({ label, value, onChange, columns }) {
  const blank = Object.fromEntries(columns.map((c) => [c.name, c.blank]));
  const update = (i, name, v) => onChange(value.map((row, j) => (j === i ? { ...row, [name]: v } : row)));
  return (
    <fieldset className="rows">
      <legend>{label}</legend>
      <table>
        <thead>
          <tr>
            {columns.map((c) => <th key={c.name}>{c.label}</th>)}
            <th />
          </tr>
        </thead>
        <tbody>
          {value.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.name}>
                  {c.input({ bare: true, label: `${c.label} ${i + 1}`, value: row[c.name], onChange: (v) => update(i, c.name, v) })}
                </td>
              ))}
              <td>
                <button type="button" className="link" onClick={() => onChange(value.filter((_, j) => j !== i))}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="secondary" onClick={() => onChange([...value, blank])}>Add a row</button>
    </fieldset>
  );
}

const FORMATS = {
  money: (v) => (Number(v) / 100).toFixed(2),
  'yes/no': (v) => (v ? 'Yes' : 'No'),
};

/** Records as a table. columns: [{ name, label, format }]; actions: [{ label, run(row) }] */
export function Table({ columns, rows, actions = [] }) {
  if (rows === null) return <p className="muted">Loading…</p>;
  if (!rows.length) return <p className="muted">Nothing to show yet.</p>;
  return (
    <div className="table-wrap">
      <table className="records">
        <thead>
          <tr>
            {columns.map((c) => <th key={c.name} className={c.format === 'money' ? 'num' : ''}>{c.label}</th>)}
            {actions.length > 0 && <th />}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.name} className={c.format === 'money' ? 'num' : ''}>
                  {(FORMATS[c.format] || String)(row[c.name])}
                </td>
              ))}
              {actions.length > 0 && (
                <td className="actions">
                  {actions.map((a) => (
                    <button key={a.label} type="button" className="secondary" onClick={() => a.run(row)}>
                      {a.label}
                    </button>
                  ))}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
'''

API = r'''// Talking to the backend. Every path is under /api, which Vite (npm run dev) and nginx
// (Docker, Kubernetes) forward to the backend with the /api prefix removed.

async function answer(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `the request failed (${res.status})`);
  return data;
}

/** Run a flow: POST (or PUT, DELETE) its path with the payload; resolves to its response. */
export async function send(method, path, body) {
  return answer(await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }));
}

/** The records of an entity whose fields equal `filters`. */
export async function records(entity, filters = {}) {
  const query = new URLSearchParams(filters).toString();
  return answer(await fetch(`/api/data/${entity}${query ? `?${query}` : ''}`));
}

/** "Order {order_id} placed" with the response's fields filled in. */
export function fill(template, values) {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ''));
}

/** A fresh identifier for a "generated" field: PREFIX-XXXXXX. */
export function newId(prefix) {
  return `${prefix}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
}
'''

STYLES = '''/* Generated: a plain, readable look. Edit freely. */
:root {
  --bg: #f6f7f9;
  --panel: #ffffff;
  --ink: #1d2330;
  --muted: #667085;
  --line: #e3e6ec;
  --accent: #3657d6;
  --accent-ink: #ffffff;
  --ok-bg: #e8f6ee;
  --ok-ink: #17643a;
  --err-bg: #fdecec;
  --err-ink: #a12a2a;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  color: var(--ink);
  background: var(--bg);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161b; --panel: #1c1f26; --ink: #e7e9ee; --muted: #9aa3b2; --line: #2c313b;
    --accent: #7d95ff; --accent-ink: #0e1220; --ok-bg: #173826; --ok-ink: #8fe0b0; --err-bg: #3d1d1d; --err-ink: #ffb1b1;
  }
}
* { box-sizing: border-box; }
body { margin: 0; }
.app { display: flex; min-height: 100vh; }
.sidebar { width: 220px; flex-shrink: 0; background: var(--panel); border-right: 1px solid var(--line);
  padding: 20px 12px; display: flex; flex-direction: column; gap: 2px; }
.brand { font-weight: 700; padding: 0 10px 16px; }
.sidebar a { color: var(--ink); text-decoration: none; padding: 8px 10px; border-radius: 6px; }
.sidebar a.active { background: var(--accent); color: var(--accent-ink); }
.content { flex: 1; padding: 32px clamp(16px, 4vw, 48px); min-width: 0; }
.page { max-width: 880px; }
h1 { font-size: 1.5rem; margin: 0 0 20px; }
form, .records, .rows { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }
form { padding: 20px; display: flex; flex-direction: column; gap: 16px; max-width: 560px; }
.field { display: flex; flex-direction: column; gap: 6px; }
label, legend, th { font-size: 0.85rem; color: var(--muted); font-weight: 600; }
input, textarea, select { font: inherit; color: var(--ink); background: var(--bg); border: 1px solid var(--line);
  border-radius: 6px; padding: 8px 10px; width: 100%; }
input[type='checkbox'] { width: auto; align-self: flex-start; }
input[readonly] { color: var(--muted); }
button { font: inherit; border: 0; border-radius: 6px; padding: 9px 16px; cursor: pointer;
  background: var(--accent); color: var(--accent-ink); font-weight: 600; align-self: flex-start; }
button:disabled { opacity: 0.6; cursor: default; }
button.secondary { background: transparent; color: var(--accent); border: 1px solid var(--line); padding: 6px 12px; }
button.link { background: none; color: var(--muted); padding: 4px; font-weight: 400; }
.rows { padding: 12px; margin: 0; }
.rows table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
.rows td { padding: 4px; }
.table-wrap { overflow-x: auto; }
.records { width: 100%; border-collapse: separate; border-spacing: 0; overflow: hidden; }
.records th, .records td { text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--line); }
.records tr:last-child td { border-bottom: 0; }
.num { text-align: right !important; font-variant-numeric: tabular-nums; }
.actions { white-space: nowrap; text-align: right; }
.notice { padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; }
.notice.ok { background: var(--ok-bg); color: var(--ok-ink); }
.notice.error { background: var(--err-bg); color: var(--err-ink); }
.muted { color: var(--muted); }
@media (max-width: 640px) {
  .app { flex-direction: column; }
  .sidebar { width: auto; flex-direction: row; flex-wrap: wrap; border-right: 0; border-bottom: 1px solid var(--line); }
  .brand { width: 100%; padding-bottom: 8px; }
}
'''

NGINX = r'''# Serves the built app, and forwards /api/* to the backend (API_URL) without the /api prefix.
server {
  listen 80;
  root /usr/share/nginx/html;

  location /api/ {
    proxy_pass ${API_URL}/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }

  location / {
    try_files $uri /index.html;
  }
}
'''

DOCKERFILE = '''FROM node:22-slim AS build
WORKDIR /web
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# nginx fills ${API_URL} in the template when the container starts
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /web/dist /usr/share/nginx/html
ENV API_URL=http://app:8000
EXPOSE 80
'''

TEST_UTILS = '''// Helpers for the screen tests: a fake backend, and rendering the app at a path.
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import App from './App.jsx';

/** routes: {'POST /api/orders': [200, {...}], 'GET /api/data/order': [200, [...]]}; others answer 200 []. */
export function fakeBackend(routes) {
  const fetch = vi.fn(async (url, init = {}) => {
    const [status, body] = routes[`${init.method || 'GET'} ${url.split('?')[0]}`] || [200, []];
    return { ok: status < 400, status, json: async () => body };
  });
  globalThis.fetch = fetch;
  return fetch;
}

export function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </MemoryRouter>,
  );
}

/** The JSON body of the fetch call to this method and path. */
export function sent(fetch, method, path) {
  const call = fetch.mock.calls.find(([url, init = {}]) => url === `/api${path}` && (init.method || 'GET') === method);
  return call && JSON.parse(call[1].body);
}
'''


# ---------------------------------------------------------------- per screen

def _prefix(name):
    base = name[:-3] if name.endswith('_id') else name
    return (base.replace('_', '')[:6] or 'ID').upper()


def _blank(f):
    """The field's starting value, as JavaScript."""
    if f.widget == 'generated':
        return f'newId({js(_prefix(f.name))})'
    if f.widget == 'choice':
        return js(f.choices[0])
    if f.widget == 'rows':
        return '[' + _row_blank(f) + ']'
    return {'int': '0', 'bool': 'false', 'str list': '[]', 'int list': '[]'}.get(f.type, "''")


def _row_blank(f):
    return '{ ' + ', '.join(f'{s.name}: {_blank(s)}' for s in f.rows) + ' }'


def _control(f, props):
    """The JSX element for a widget, given its props text."""
    w = f.widget
    if w in ('text', 'email', 'date', 'generated'):
        extra = {'email': ' type="email"', 'date': ' type="date"', 'generated': ' readOnly'}.get(w, '')
        return f'<TextInput {props}{extra} />'
    if w == 'long text':
        return f'<LongText {props} />'
    if w == 'number':
        return f'<NumberInput {props} />'
    if w == 'money':
        return f'<MoneyInput {props} />'
    if w == 'checkbox':
        return f'<Checkbox {props} />'
    if w == 'choice':
        return f'<Choice {props} options={{{js(f.choices)}}} />'
    if w == 'list':
        return f'<ListInput {props}{" numbers" if f.type == "int list" else ""} />'
    raise ValueError(w)


def _widget_names(fields):
    names = set()
    for f in fields:
        if f.widget == 'rows':
            names.add('Rows')
            names |= _widget_names(f.rows)
            continue
        names.add({'text': 'TextInput', 'email': 'TextInput', 'date': 'TextInput', 'generated': 'TextInput',
                   'long text': 'LongText', 'number': 'NumberInput', 'money': 'MoneyInput', 'checkbox': 'Checkbox',
                   'choice': 'Choice', 'list': 'ListInput'}[f.widget])
    return names


def form_screen(s, screens):
    comp = camel(s.name)
    target = next((x for x in screens if x.name == s.go_to), None)
    lines = []
    for f in s.fields:
        if f.widget == 'rows':
            cols = ',\n'.join(
                f'            {{ name: {js(r.name)}, label: {js(r.label)}, blank: {_blank(r)}, '
                f'input: (props) => {_control(r, "{...props}")} }}' for r in f.rows)
            lines.append(f'        <Rows label={attr(f.label)} value={{values.{f.name}}} onChange={{set({js(f.name)})}}\n'
                         f'          columns={{[\n{cols},\n          ]}} />')
        else:
            lines.append('        ' + _control(f, f'label={attr(f.label)} value={{values.{f.name}}} onChange={{set({js(f.name)})}}'))
    initial = ',\n'.join(f'    {f.name}: {_blank(f)}' for f in s.fields)
    message = s.message or ('Sent. It runs in the background.' if s.is_async else 'Done.')
    if target:
        after = (f'      navigate({js(route(target))}, {{ state: {{ notice: {{ kind: \'ok\', text: fill({js(message)}, response) }} }} }});'
                 if s.message or not s.go_to else f'      navigate({js(route(target))});')
    else:
        after = (f'      setNotice({{ kind: \'ok\', text: fill({js(message)}, response) }});\n'
                 f'      setValues(initial());')
    uses_new_id = any(f.widget == 'generated' for f in s.fields) or any(
        r.widget == 'generated' for f in s.fields for r in f.rows)
    api_imports = ', '.join(['fill'] + (['newId'] if uses_new_id else []) + ['send'])
    return f'''import {{ useState }} from 'react';
{"import { useNavigate } from 'react-router-dom';" + chr(10) if target else ''}import {{ {api_imports} }} from '../api.js';
import {{ {', '.join(sorted(_widget_names(s.fields) | {'Page'}))} }} from '../ui.jsx';

// The form's starting values: every field flow {s.flow} takes.
const initial = () => ({{
{initial},
}});

/** {s.title}: runs flow {s.flow} ({s.method} {s.path}). */
export default function {comp}() {{
{"  const navigate = useNavigate();" + chr(10) if target else ''}  const [values, setValues] = useState(initial);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (name) => (value) => setValues((v) => ({{ ...v, [name]: value }}));

  async function submit(event) {{
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {{
      const response = await send({js(s.method)}, {js(s.path)}, values);
{after}
    }} catch (e) {{
      setNotice({{ kind: 'error', text: e.message }});
    }} finally {{
      setBusy(false);
    }}
  }}

  return (
    <Page title={attr(s.title)} notice={{notice}}>
      <form onSubmit={{submit}}>
{chr(10).join(lines)}
        <button type="submit" disabled={{busy}}>{text(s.submit)}</button>
      </form>
    </Page>
  );
}}
'''


def list_screen(s):
    comp = camel(s.name)
    cols = ',\n'.join(f'  {{ name: {js(c.name)}, label: {js(c.label)}, format: {js(c.format)} }}' for c in s.columns)
    runs, actions = [], []
    for i, a in enumerate(s.actions):
        fn = f'run{i + 1}' if len(s.actions) > 1 else 'run'
        body = ', '.join(f'{k}: row.{v}' if kind == 'field' else f'{k}: {js(v)}' for k, (kind, v) in a.payload.items())
        runs.append(f'''  /** {a.label}: runs flow {a.flow} ({a.method} {a.path}) with the row's values. */
  async function {fn}(row) {{
    try {{
      await send({js(a.method)}, {js(a.path)}, {{ {body} }});
      setNotice({{ kind: 'ok', text: {js(a.label + ': done.')} }});
      load();
    }} catch (e) {{
      setNotice({{ kind: 'error', text: e.message }});
    }}
  }}''')
        actions.append(f'{{ label: {js(a.label)}, run: {fn} }}' if fn != 'run' else f'{{ label: {js(a.label)}, run }}')
    return f'''import {{ useCallback, useEffect, useState }} from 'react';
import {{ records{', send' if s.actions else ''} }} from '../api.js';
import {{ Page, Table }} from '../ui.jsx';

const COLUMNS = [
{cols},
];
const FILTER = {js(s.filters)};

/** {s.title}: the {s.entity} records{' where ' + ', '.join(f'{k} = {js(v)}' for k, v in s.filters.items()) if s.filters else ''}. */
export default function {comp}() {{
  const [rows, setRows] = useState(null);
  const [notice, setNotice] = useState(null);
  const load = useCallback(
    () => records({js(s.entity)}, FILTER).then(setRows, (e) => setNotice({{ kind: 'error', text: e.message }})),
    [],
  );
  useEffect(() => {{
    load();
  }}, [load]);
{chr(10) + chr(10).join(runs) + chr(10) if runs else ''}
  return (
    <Page title={attr(s.title)} notice={{notice}}>
      <Table columns={{COLUMNS}} rows={{rows}}{' actions={[' + ', '.join(actions) + ']}' if actions else ''} />
    </Page>
  );
}}
'''


# ---------------------------------------------------------------- tests

def _sample(f, rng):
    """(what the test types, what the form should send) for one widget."""
    w = f.widget
    if w == 'email':
        return 'someone@example.com', 'someone@example.com'
    if w == 'date':
        return '2026-09-28', '2026-09-28'
    if w in ('text', 'long text'):
        v = f'{f.label} {rng.randint(1, 99)}'
        return v, v
    if w == 'number':
        n = rng.randint(2, 99)
        return str(n), n
    if w == 'money':
        cents = rng.randint(101, 99999)
        return f'{cents / 100:.2f}', cents
    if w == 'list':
        return ('3, 5', [3, 5]) if f.type == 'int list' else ('red, blue', ['red', 'blue'])
    if w == 'choice':
        return str(len(f.choices) - 1), f.choices[-1]
    raise ValueError(w)


def _fill(f, label, rng):
    """(JS statements that fill the control, the JS expression expected in the body)."""
    if f.widget == 'generated':
        return [], 'expect.any(String)'
    if f.widget == 'checkbox':
        return [f'fireEvent.click(screen.getByLabelText({js(label)}));'], 'true'
    typed, want = _sample(f, rng)
    return [f'fireEvent.change(screen.getByLabelText({js(label)}), {{ target: {{ value: {js(typed)} }} }});'], js(want)


def form_test(s, screens, rng):
    steps, body = [], []
    for f in s.fields:
        if f.widget == 'rows':
            row = []
            for r in f.rows:
                st, want = _fill(r, f'{r.label} 1', rng)
                steps += st
                row.append(f'{r.name}: {want}')
            body.append(f'{f.name}: [{{ {", ".join(row)} }}]')
            continue
        st, want = _fill(f, f.label, rng)
        steps += st
        body.append(f'{f.name}: {want}')
    responds = sorted(set(re_fields(s.message)))
    response = {k: f'{k.upper()}-1' for k in responds}
    shown = s.message
    for k, v in response.items():
        shown = shown.replace('{' + k + '}', v)
    expect_after = []
    if s.message or not s.go_to:
        expect_after.append(f"expect(await screen.findByText({js(shown or ('Sent. It runs in the background.' if s.is_async else 'Done.'))})).toBeTruthy();")
    if s.go_to:
        target = next(x for x in screens if x.name == s.go_to)
        expect_after.append(f"expect(await screen.findByRole('heading', {{ name: {js(target.title)} }})).toBeTruthy();")
    status = 202 if s.is_async else 200
    fill_lines = '\n'.join('    ' + x for x in steps)
    return f'''import {{ fireEvent, screen }} from '@testing-library/react';
import {{ describe, expect, it }} from 'vitest';
import {{ fakeBackend, renderAt, sent }} from '../test-utils.jsx';

describe({js(s.title)}, () => {{
  it('sends every field to {s.flow}', async () => {{
    const fetch = fakeBackend({{ {js(s.method + ' /api' + s.path)}: [{status}, {js(response)}] }});
    renderAt({js(route(s))});
{fill_lines}
    fireEvent.click(screen.getByRole('button', {{ name: {js(s.submit)} }}));
    {chr(10).join(('    ' if i else '') + x for i, x in enumerate(expect_after))}
    expect(sent(fetch, {js(s.method)}, {js(s.path)})).toEqual({{ {", ".join(body)} }});
  }});

  it('shows the error when {s.flow} refuses', async () => {{
    fakeBackend({{ {js(s.method + ' /api' + s.path)}: [422, {{ error: 'something is wrong' }}] }});
    renderAt({js(route(s))});
{fill_lines}
    fireEvent.click(screen.getByRole('button', {{ name: {js(s.submit)} }}));
    expect((await screen.findByRole('alert')).textContent).toBe('something is wrong');
  }});
}});
'''


def re_fields(template):
    import re
    return re.findall(r'\{([a-z][a-z0-9_]*)\}', template or '')


def _cell(value, fmt):
    if fmt == 'money':
        return f'{value / 100:.2f}'
    if fmt == 'yes/no':
        return 'Yes' if value else 'No'
    return str(value)


def list_test(s, entities, rng):
    rec = entities[s.entity]
    rows = []
    for i in (1, 2):
        row = {}
        for n, t in rec.fields:
            row[n] = {'int': rng.randint(100, 99999), 'bool': i == 1}.get(getattr(t, 'name', ''), f'{n}-{i}')
            if getattr(t, 'name', '') not in ('int', 'bool', 'str'):
                row[n] = []
        rows.append(row)
    first = s.columns[0]
    query = ('?' + '&'.join(f'{k}={v if not isinstance(v, bool) else str(v).lower()}' for k, v in s.filters.items())) \
        if s.filters else ''
    tests = [f'''  it('shows the {s.entity} records', async () => {{
    const fetch = fakeBackend({{ {js('GET /api/data/' + s.entity)}: [200, ROWS] }});
    renderAt({js(route(s))});
    expect(await screen.findByText({js(_cell(rows[0][first.name], first.format))})).toBeTruthy();
{"".join(f"    expect(screen.getAllByText({js(_cell(rows[1][c.name], c.format))}).length).toBeGreaterThan(0);{chr(10)}" for c in s.columns)}    expect(fetch.mock.calls[0][0]).toBe({js('/api/data/' + s.entity + query)});
  }});''']
    for a in s.actions:
        body = {k: (rows[0][v] if kind == 'field' else v) for k, (kind, v) in a.payload.items()}
        tests.append(f'''  it('{a.label.replace("'", "")} runs {a.flow} with the row', async () => {{
    const fetch = fakeBackend({{ {js('GET /api/data/' + s.entity)}: [200, ROWS], {js(a.method + ' /api' + a.path)}: [200, {{}}] }});
    renderAt({js(route(s))});
    fireEvent.click((await screen.findAllByRole('button', {{ name: {js(a.label)} }}))[0]);
    expect(await screen.findByText({js(a.label + ': done.')})).toBeTruthy();
    expect(sent(fetch, {js(a.method)}, {js(a.path)})).toEqual({js(body)});
  }});''')
    return f'''import {{ fireEvent, screen }} from '@testing-library/react';
import {{ describe, expect, it }} from 'vitest';
import {{ fakeBackend, renderAt, sent }} from '../test-utils.jsx';

const ROWS = {js(rows)};

describe({js(s.title)}, () => {{
{chr(10).join(tests)}
}});
'''


# ---------------------------------------------------------------- the app

PACKAGE = {
    'private': True, 'version': '0.1.0', 'type': 'module',
    'scripts': {'dev': 'vite', 'build': 'vite build', 'preview': 'vite preview', 'test': 'vitest run'},
    'dependencies': {'react': '^18.3.1', 'react-dom': '^18.3.1', 'react-router-dom': '^6.28.0'},
    'devDependencies': {'@testing-library/dom': '^10.4.0', '@testing-library/react': '^16.1.0',
                        '@vitejs/plugin-react': '^4.3.4', 'jsdom': '^25.0.1', 'vite': '^5.4.11',
                        'vitest': '^2.1.8'},
}


def generate_web(system, api_port):
    screens = system.screens
    if not screens:
        return {}
    rng = random.Random(0)
    root = f'{system.name}/web'
    comps = [(s, camel(s.name)) for s in screens]
    imports = '\n'.join(f"import {c} from './screens/{c}.jsx';" for _, c in comps)
    nav = ',\n'.join(f'  {{ path: {js(route(s))}, title: {js(s.title)} }}' for s, _ in comps)
    routes = '\n'.join(f'        <Route path={js(route(s))} element={{<{c} />}} />' for s, c in comps)
    files = {
        f'{root}/package.json': json.dumps({'name': f'{system.name}-web', **PACKAGE}, indent=2) + '\n',
        f'{root}/vite.config.js': f'''import {{ defineConfig }} from 'vite';
import react from '@vitejs/plugin-react';

// npm run dev: the app on http://localhost:5173, with /api forwarded to the backend.
const API_URL = process.env.API_URL || 'http://localhost:{api_port}';

export default defineConfig({{
  plugins: [react()],
  server: {{
    port: 5173,
    proxy: {{ '/api': {{ target: API_URL, changeOrigin: true, rewrite: (path) => path.replace(/^\\/api/, '') }} }},
  }},
  test: {{ environment: 'jsdom', setupFiles: ['./src/test-setup.js'] }},
}});
''',
        f'{root}/index.html': f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{label_of(system.name.replace('-', '_'))}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
''',
        f'{root}/src/main.jsx': '''import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
''',
        f'{root}/src/App.jsx': f'''// The screens, from the spec's "## Screen:" sections, in the order they were written.
import {{ Navigate, Route, Routes }} from 'react-router-dom';
import {{ Layout }} from './ui.jsx';
{imports}

export const SCREENS = [
{nav},
];

export default function App() {{
  return (
    <Layout title={attr(label_of(system.name.replace('-', '_')))} screens={{SCREENS}}>
      <Routes>
{routes}
        <Route path="*" element={{<Navigate to={{SCREENS[0].path}} replace />}} />
      </Routes>
    </Layout>
  );
}}
''',
        f'{root}/src/ui.jsx': UI,
        f'{root}/src/api.js': API,
        f'{root}/src/styles.css': STYLES,
        f'{root}/src/test-utils.jsx': TEST_UTILS,
        f'{root}/src/test-setup.js': '''import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(cleanup);
''',
        f'{root}/nginx.conf.template': NGINX,
        f'{root}/Dockerfile': DOCKERFILE.replace('http://app:8000', f'http://app:{api_port}'),
        f'{root}/.dockerignore': 'node_modules\ndist\n',
        f'{root}/.gitignore': 'node_modules\ndist\n',
    }
    for s, c in comps:
        if s.kind == 'form':
            files[f'{root}/src/screens/{c}.jsx'] = form_screen(s, screens)
            files[f'{root}/src/screens/{c}.test.jsx'] = form_test(s, screens, rng)
        else:
            files[f'{root}/src/screens/{c}.jsx'] = list_screen(s)
            files[f'{root}/src/screens/{c}.test.jsx'] = list_test(s, system.entities, rng)
    return files


def readme_section(system, api_port):
    if not system.screens:
        return []
    lines = ['## Web app', '',
             'A React app for the screens in the spec is in `web/`. It calls the API through `/api`.', '',
             '```bash', 'cd web', 'npm install', 'npm test                       # renders each screen and checks what it sends',
             f'npm run dev                    # http://localhost:5173 (the API must be running on {api_port})', '```', '',
             '| Screen | Shows |', '|---|---|']
    for s in system.screens:
        what = f'a form for `{s.flow}` ({s.method} {s.path})' if s.kind == 'form' else f'the `{s.entity}` records'
        lines.append(f'| {s.title} (`{route(s)}`) | {what} |')
    return lines + ['']
