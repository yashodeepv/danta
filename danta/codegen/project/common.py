"""common.py - What every project generator shares: the system, names, types."""

import re
from dataclasses import dataclass, field
from typing import Dict, List

from danta.ir2 import graph as g
from danta.ir2.types import BOOL, INT, STR, ListT, RecordT


@dataclass
class System:
    """Everything a project is generated from."""
    name: str                                   # 'shop-orders'
    description: str
    flows: List[g.Flow]
    scenarios: Dict[str, dict] = field(default_factory=dict)     # flow name -> {scenario name: scenario}
    screens: list = field(default_factory=list)                   # danta.ui.model.Screen

    @property
    def services(self):
        out = {}
        for f in self.flows:
            for s, ops in f.services.items():
                out.setdefault(s, {}).update(ops)
        return out

    @property
    def entities(self):
        out = {}
        for f in self.flows:
            out.update(f.entities)
        return out


def data_entities(system):
    """{entity: {field: 'str' | 'int' | 'bool'}} for the entities a list screen shows: the
    records GET /data/<entity> serves, filterable by these fields."""
    out = {}
    for s in system.screens:
        if s.kind == 'list':
            rec = system.entities[s.entity]
            out[s.entity] = {n: t.name for n, t in rec.fields if t in (INT, STR, BOOL)}
    return out


def fake_outputs(system):
    """{(service, op): {field: value}} for every service operation: what the call returned
    in the flow's longest passing test run, so the generated fakes walk the happy path
    (a fake that answers is_valid = false would fail every request). An operation no
    passing run calls gets plausible samples: true, 1, "<field>-1"."""
    seen = {}
    for f in system.flows:
        calls = {s.id: s for s in f.steps if isinstance(s, g.Call)}
        runs = sorted(system.scenarios.get(f.name, {}).values(),
                      key=lambda sc: -len(sc.get('expect', {}).get('path', [])))
        for sc in runs:
            if sc.get('expect', {}).get('status') != 'ok':
                continue
            for sid, mock in sc.get('mocks', {}).items():
                attempt = mock[-1] if isinstance(mock, list) else mock
                if sid in calls and isinstance(attempt, dict) and 'ok' in attempt:
                    seen.setdefault((calls[sid].service, calls[sid].op), attempt['ok'])
    out = {}
    for s, ops in system.services.items():
        for op, sig in ops.items():
            got = seen.get((s, op), {})
            out[(s, op)] = {n: got[n] if n in got else sample_value(t, n) for n, t in sig.output.fields}
    return out


def sample_value(t, name=''):
    if t == INT:
        return 1
    if t == BOOL:
        return True
    if t == STR:
        return f'{name}-1' if name else 'sample'
    if isinstance(t, RecordT):
        return {n: sample_value(ft, n) for n, ft in t.fields}
    return []


def snake(name):
    return re.sub(r'[^a-z0-9_]', '_', name.lower()).strip('_') or 'app'


def camel(name):
    return ''.join(p[:1].upper() + p[1:] for p in re.split(r'[^a-zA-Z0-9]', name) if p)


def trigger_line(flow):
    t = flow.trigger()
    if t.source == 'http':
        return f"{t.config['method']} {t.config['path']}"
    if t.source == 'event':
        return f"event {t.config['name']}"
    if t.source == 'topic':
        return f"topic {t.config['name']}"
    return f"schedule \"{t.config['cron']}\""


class TypeNamer:
    """Gives every record type a class name, and writes it once."""

    def __init__(self):
        self.defs = []                          # (name, RecordT), in dependency order
        self.names = {}

    def record(self, rec, name):
        key = rec
        if key in self.names:
            return self.names[key]
        base, n = name, 2
        while name in {d for d, _ in self.defs}:
            name, n = f'{base}{n}', n + 1
        for fname, ft in rec.fields:           # nested records first
            self.annotate(ft, name + camel(fname))
        self.names[key] = name
        self.defs.append((name, rec))
        return name

    def annotate(self, t, hint):
        """Register nested records; the language printers spell the type."""
        if isinstance(t, RecordT):
            return self.record(t, hint)
        if isinstance(t, ListT):
            return self.annotate(t.elem, hint + 'Item')
        return None


def py_type(t, namer):
    if t == INT:
        return 'int'
    if t == STR:
        return 'str'
    if t == BOOL:
        return 'bool'
    if isinstance(t, ListT):
        return f'List[{py_type(t.elem, namer)}]'
    if isinstance(t, RecordT):
        return namer.names[t]
    return 'Any'


def js_type(t, namer):
    if t == INT:
        return 'number'
    if t == STR:
        return 'string'
    if t == BOOL:
        return 'boolean'
    if isinstance(t, ListT):
        return f'{js_type(t.elem, namer)}[]'
    if isinstance(t, RecordT):
        return namer.names[t]
    return '*'


def collect_types(system):
    """Name every record the project exposes: entities, flow inputs, service contracts."""
    namer = TypeNamer()
    for e, rec in system.entities.items():
        namer.record(rec, camel(e))
    for f in system.flows:
        namer.record(f.trigger().payload, camel(f.name) + 'Input')
    for s, ops in system.services.items():
        for op, sig in ops.items():
            namer.record(sig.input, camel(s) + camel(op) + 'Args')
            namer.record(sig.output, camel(s) + camel(op) + 'Result')
    return namer


def outline(flow):
    """Indented step titles, for READMEs."""
    lines = []
    for s in flow.steps:
        if isinstance(s, (g.Trigger, g.Join)):
            continue
        label = s.title or s.kind
        lines.append(f'- {label} ({s.kind})')
    return lines
