"""screens.py - `## Screen:` sections -> checked danta.ui.model.Screen objects.

Screens are compiled after the flows, because every screen is checked
against what it shows: a form against its flow's trigger payload and
responses, a list against its entity, an action against the flow it runs.
LANGUAGE.md §12 is the reference; the rule names here are its §9 names.
"""

import re

from danta.ir2 import graph as g
from danta.ir2.types import BOOL, INT, STR, ListT, RecordT
from danta.spec.document import SpecError
from danta.spec.text import QUOTED, split_top, unquote
from danta.spec.values import literal
from danta.ui.model import (DEFAULT_FORMAT, DEFAULT_WIDGET, FORMATS, WIDGETS, Action, Column, Field, Screen,
                           label_of)

NAME = r'[a-z][a-z0-9_]*'
STRING = r'"(?:[^"\\]|\\.)*"'
_ITEM = re.compile(rf'({NAME})(?:\s+({STRING}))?(?:\s*:\s*(.+))?')
_PLACEHOLDER = re.compile(r'\{([a-z][a-z0-9_]*)\}')


def type_name(t):
    if t in (INT, STR, BOOL):
        return t.name
    if isinstance(t, ListT) and t.elem in (INT, STR):
        return f'{t.elem.name} list'
    if isinstance(t, ListT) and isinstance(t.elem, RecordT):
        return 'record list'
    return None


def _value(raw, line):
    """A literal as a plain Python value, and its type name."""
    v, t = literal(raw, line)
    return v.v, t.name


def compile_screens(docs, flows, entities, errors):
    by_flow = {f.name: f for f in flows}
    screens, names = [], set()
    for d in docs:
        if d.name in names:
            errors.append(SpecError('unique-names', d.line, f'screen {d.name} is declared twice'))
            continue
        names.add(d.name)
        try:
            screens.append(_Screen(d, by_flow, entities, errors).compile())
        except SpecError as e:
            errors.append(e)
    for s in screens:
        if s.go_to and s.go_to not in names:
            errors.append(SpecError('screen-after', s.line, f'"go to {s.go_to}": there is no screen {s.go_to}'))
    return screens


class _Screen:
    def __init__(self, doc, flows, entities, errors):
        self.doc, self.flows, self.entities, self.errors = doc, flows, entities, errors

    def err(self, rule, line, msg):
        self.errors.append(SpecError(rule, line, msg))

    def prop(self, key):
        return self.doc.props.get(key, (self.doc.line, None))

    def compile(self):
        d = self.doc
        line, title = self.prop('Title')
        if not title:
            raise SpecError('layout', d.line, f'screen {d.name} needs a "Title:"')
        line, shows = self.prop('Shows')
        m = re.fullmatch(rf'(form for|list of)\s+({NAME})', shows or '')
        if not m:
            raise SpecError('screen-kind', line, 'expected "Shows: form for <flow>" or "Shows: list of <entity>"')
        screen = Screen(d.name, title, 'form' if m.group(1) == 'form for' else 'list', d.line)
        allowed = {'form': {'Title', 'Shows', 'Fields', 'Submit', 'After'},
                   'list': {'Title', 'Shows', 'Columns', 'Filter', 'Actions'}}[screen.kind]
        for key, val in list(d.props.items()) + [(k, (d.line, None)) for k in d.lists]:
            if key not in allowed:
                self.err('screen-kind', val[0], f'a {screen.kind} screen has no "{key}:"')
        if screen.kind == 'form':
            self.form(screen, m.group(2))
        else:
            self.list(screen, m.group(2))
        return screen

    def http_flow(self, name, line):
        f = self.flows.get(name)
        if f is None:
            raise SpecError('screen-flow', line, f'there is no flow {name}')
        t = f.trigger()
        if t.source != 'http' or t.config['method'] == 'GET':
            raise SpecError('screen-flow', line, f'flow {name} is not started by an HTTP POST, PUT or DELETE, '
                                                 'so a screen cannot run it')
        return f, t

    # ------------------------------------------------------------------ forms

    def form(self, screen, flow_name):
        line = self.prop('Shows')[0]
        f, t = self.http_flow(flow_name, line)
        screen.flow, screen.method, screen.path = f.name, t.config['method'], t.config['path']
        screen.is_async = f.mode == 'async'
        payload = dict(t.payload.fields)
        items = self.doc.lists.get('Fields')
        if items is None:
            raise SpecError('screen-fields', self.doc.line, 'a form lists its "Fields:"')
        seen = set()
        for n, text in items:
            fld = self.field(text, n, payload, f'flow {f.name}\'s trigger')
            if fld is None:
                continue
            if fld.name in seen:
                self.err('screen-fields', n, f'field {fld.name} is listed twice')
            seen.add(fld.name)
            screen.fields.append(fld)
        missing = [k for k in payload if k not in seen]
        if missing:
            self.err('screen-fields', self.doc.line,
                     f'the form must fill every field {f.name} takes; missing: {", ".join(missing)}')
        n, submit = self.prop('Submit')
        if submit:
            if not QUOTED.fullmatch(submit):
                self.err('syntax', n, 'expected Submit: "<button label>"')
            else:
                screen.submit = unquote(submit)
        self.after(screen, f)

    def field(self, text, line, available, where, nested=False):
        m = _ITEM.fullmatch(text)
        if not m:
            self.err('syntax', line, 'expected "- <field> "<label>": <widget>" (label and widget optional)')
            return None
        name, label, spec = m.group(1), m.group(2), (m.group(3) or '').strip()
        if name not in available:
            self.err('screen-fields', line, f'{where} has no field {name}')
            return None
        t = type_name(available[name])
        if t is None:
            self.err('widget-type', line, f'{name} has a type no widget edits')
            return None
        fld = Field(name, unquote(label) if label else label_of(name), '', t)
        if spec.startswith('choice of '):
            fld.widget = 'choice'
            for raw in split_top(spec[len('choice of '):], ','):
                try:
                    v, vt = _value(raw, line)
                except SpecError as e:
                    self.errors.append(e)
                    continue
                if vt != t:
                    self.err('widget-type', line, f'choice {raw} is a {vt}, but {name} is a {t}')
                fld.choices.append(v)
        elif spec.startswith('rows of ') and not nested:
            fld.widget = 'rows'
            elem = available[name].elem if isinstance(available[name], ListT) else None
            sub = dict(elem.fields) if isinstance(elem, RecordT) else {}
            for part in split_top(spec[len('rows of '):], ','):
                s = self.field(part, line, sub, f'each {name} row', nested=True)
                if s is not None:
                    fld.rows.append(s)
            missing = [k for k in sub if k not in {s.name for s in fld.rows}]
            if missing:
                self.err('screen-fields', line, f'the rows of {name} must include {", ".join(missing)}')
        else:
            fld.widget = spec or DEFAULT_WIDGET.get(t, '')
            if not fld.widget:
                self.err('widget-type', line, f'{name} is a list of records: use "rows of <field>, ..."')
                return None
            if fld.widget not in WIDGETS or fld.widget in ('choice', 'rows'):
                self.err('widget-type', line, f'unknown widget "{fld.widget}"; widgets are '
                                              + ', '.join(sorted(WIDGETS)))
                return None
        if t not in WIDGETS[fld.widget]:
            self.err('widget-type', line, f'a {fld.widget} widget cannot edit {name}, a {t}')
        return fld

    def after(self, screen, flow):
        n, after = self.prop('After')
        if not after:
            return
        m = re.fullmatch(rf'(?:show\s+({STRING}))?\s*,?\s*(?:(?:then\s+)?go to\s+({NAME}))?', after)
        if not m or not (m.group(1) or m.group(2)):
            self.err('syntax', n, 'expected After: show "<message>", then go to <screen>  (either part alone is fine)')
            return
        if m.group(1):
            screen.message = unquote(m.group(1))
            responds = {k for s in flow.steps if isinstance(s, g.End) and s.status == 'ok' and s.response
                        for k in s.response}
            for ph in _PLACEHOLDER.findall(screen.message):
                if ph not in responds:
                    why = 'it runs in the background and responds with nothing' if screen.is_async else \
                        f'it responds with {", ".join(sorted(responds)) or "nothing"}'
                    self.err('screen-after', n, f'{{{ph}}} is not in {flow.name}\'s response: {why}')
        screen.go_to = m.group(2)

    # ------------------------------------------------------------------ lists

    def list(self, screen, entity):
        line = self.prop('Shows')[0]
        rec = self.entities.get(entity)
        if rec is None:
            raise SpecError('known-entity', line, f'there is no entity {entity}')
        screen.entity = entity
        fields = dict(rec.fields)
        items = self.doc.lists.get('Columns')
        if items is None:
            raise SpecError('screen-columns', self.doc.line, 'a list shows its "Columns:"')
        for n, text in items:
            m = _ITEM.fullmatch(text)
            if not m:
                self.err('syntax', n, 'expected "- <field> "<label>": <format>" (label and format optional)')
                continue
            name, label, fmt = m.group(1), m.group(2), (m.group(3) or '').strip()
            if name not in fields:
                self.err('screen-columns', n, f'entity {entity} has no field {name}')
                continue
            t = type_name(fields[name])
            fmt = fmt or DEFAULT_FORMAT.get(t, '')
            if fmt not in FORMATS or t not in FORMATS[fmt]:
                self.err('widget-type', n, f'{name} is a {t}; a column shows it as '
                         + ', '.join(k for k, ts in FORMATS.items() if t in ts) if t else f'{name} cannot be a column')
                continue
            screen.columns.append(Column(name, unquote(label) if label else label_of(name), fmt))
        n, flt = self.prop('Filter')
        if flt:
            for part in split_top(flt, ' and '):
                m = re.fullmatch(rf'({NAME})\s*=\s*(.+)', part)
                if not m:
                    self.err('syntax', n, 'expected Filter: <field> = <value> and <field> = <value> ...')
                    continue
                if m.group(1) not in fields:
                    self.err('screen-filter', n, f'entity {entity} has no field {m.group(1)}')
                    continue
                try:
                    v, vt = _value(m.group(2), n)
                except SpecError as e:
                    self.errors.append(e)
                    continue
                if vt != type_name(fields[m.group(1)]):
                    self.err('screen-filter', n, f'{m.group(1)} is a {type_name(fields[m.group(1)])}, not a {vt}')
                screen.filters[m.group(1)] = v
        for n, text in self.doc.lists.get('Actions', []):
            a = self.action(text, n, fields)
            if a:
                screen.actions.append(a)

    def action(self, text, line, row):
        m = re.fullmatch(rf'({STRING})\s*:\s*({NAME})(?:\s+with\s+(.+))?', text)
        if not m:
            self.err('syntax', line, 'expected - "<label>": <flow> with <field>, <field> = <row field or value>, ...')
            return None
        try:
            f, t = self.http_flow(m.group(2), line)
        except SpecError as e:
            self.errors.append(e)
            return None
        payload = dict(t.payload.fields)
        out = {}
        for part in split_top(m.group(3), ',') if m.group(3) else []:
            pm = re.fullmatch(rf'({NAME})(?:\s*=\s*(.+))?', part)
            if not pm:
                self.err('syntax', line, f'expected <field> or <field> = <row field or value>, not "{part}"')
                continue
            name, src = pm.group(1), (pm.group(2) or pm.group(1)).strip()
            if name not in payload:
                self.err('screen-action', line, f'flow {f.name} takes no field {name}')
                continue
            want = type_name(payload[name])
            if re.fullmatch(NAME, src) and src not in ('true', 'false'):
                if src not in row:
                    self.err('screen-action', line, f'the row has no field {src}')
                    continue
                have = type_name(row[src])
                out[name] = ('field', src)
            else:
                try:
                    v, have = _value(src, line)
                except SpecError as e:
                    self.errors.append(e)
                    continue
                out[name] = ('value', v)
            if have != want:
                self.err('screen-action', line, f'{f.name} takes {name} as a {want}, not a {have}')
        missing = [k for k in payload if k not in out]
        if missing:
            self.err('screen-action', line, f'flow {f.name} also needs {", ".join(missing)}')
        return Action(unquote(m.group(1)), f.name, t.config['method'], t.config['path'], out)
