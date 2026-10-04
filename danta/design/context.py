"""context.py — Extract designer-relevant information from a compiled backend spec.

The result is injected into the design skill prompt as {{system_context}} so the
LLM knows exactly what fields, flows, and screens are available before it writes
a design spec.

Usage:
    from danta.spec import compile_spec
    from danta.design.context import extract, format_for_prompt

    res = compile_spec(spec_text)
    ctx = extract(res)
    prompt_section = format_for_prompt(ctx)
"""

from __future__ import annotations

from danta.ir2 import graph as g
from danta.ir2.types import RecordT, ListT, BOOL, INT, STR


def _type_str(t) -> str:
    if t is INT:
        return 'int'
    if t is STR:
        return 'str'
    if t is BOOL:
        return 'bool'
    if isinstance(t, ListT):
        inner = _type_str(t.elem)
        return f'list of {inner}'
    if isinstance(t, RecordT):
        fields = ', '.join(f'{n} {_type_str(ft)}' for n, ft in t.fields)
        return f'({fields})'
    return str(t)


def _trigger_inputs(flow) -> list[dict]:
    t = flow.trigger()
    if not hasattr(t, 'payload') or not isinstance(t.payload, RecordT):
        return []
    return [{'name': name, 'type': _type_str(ft)} for name, ft in t.payload.fields]


def _flow_outputs(flow) -> list[str]:
    outputs = set()
    for s in flow.steps:
        if isinstance(s, g.End) and s.status == 'ok' and s.response:
            outputs.update(s.response.keys())
    return sorted(outputs)


def extract(compiled) -> dict:
    """Return a structured context dict from a compile_spec() result.
    Safe to call even when compiled.errors is non-empty."""

    # Entities: name -> list of {name, type}
    entities = {}
    for ename, rec in (compiled.entities or {}).items():
        if isinstance(rec, RecordT):
            entities[ename] = [{'name': n, 'type': _type_str(t)} for n, t in rec.fields]

    # Flows: name -> {trigger, mode, inputs, outputs}
    flows = {}
    for flow in (compiled.flows or []):
        t = flow.trigger()
        trigger_desc = ''
        if t.source == 'http':
            trigger_desc = f"{t.config.get('method', 'POST')} {t.config.get('path', '')}"
        elif t.source == 'schedule':
            trigger_desc = f"schedule {t.config.get('cron', '')}"
        elif t.source in ('event', 'topic'):
            trigger_desc = f"{t.source} {t.config.get('name', '')}"
        method = t.config.get('method', 'POST') if t.source == 'http' else ''
        path = t.config.get('path', '') if t.source == 'http' else ''
        flows[flow.name] = {
            'trigger': trigger_desc,
            'method': method,
            'path': path,
            'mode': flow.mode,
            'inputs': _trigger_inputs(flow),
            'outputs': _flow_outputs(flow),
        }

    # Screens: what the backend already declared
    screens = []
    for s in (compiled.screens or []):
        entry = {
            'name': s.name,
            'title': s.title,
            'kind': s.kind,
        }
        if s.kind == 'form':
            entry['flow'] = s.flow
            entry['path'] = s.path
            entry['fields'] = [
                {'name': f.name, 'label': f.label, 'widget': f.widget, 'type': f.type}
                for f in s.fields
            ]
        else:
            entry['entity'] = s.entity
            entry['columns'] = [
                {'name': c.name, 'label': c.label, 'format': c.format}
                for c in s.columns
            ]
        screens.append(entry)

    return {
        'system': compiled.system,
        'description': compiled.description,
        'entities': entities,
        'flows': flows,
        'screens': screens,
    }


def format_for_prompt(ctx: dict) -> str:
    """Format the context dict as a readable block for injection into the design skill prompt."""
    lines = [f'System: {ctx["system"]}']
    if ctx.get('description'):
        lines.append(f'Description: {ctx["description"]}')
    lines.append('')

    if ctx['entities']:
        lines.append('Entities (persistent data — use in List and Stats components):')
        for name, fields in ctx['entities'].items():
            field_str = ', '.join(f'{f["name"]} {f["type"]}' for f in fields)
            lines.append(f'  {name}: {field_str}')
        lines.append('')

    if ctx['flows']:
        lines.append('Flows (backend logic — reference by name in Form components):')
        for name, info in ctx['flows'].items():
            inputs = ', '.join(f'{f["name"]} {f["type"]}' for f in info['inputs'])
            outputs = ', '.join(info['outputs'])
            endpoint = ''
            if info.get('method') and info.get('path'):
                endpoint = f'  endpoint: {info["method"]} {info["path"]}'
            lines.append(f'  {name}  [{info["trigger"]}]  mode: {info["mode"]}')
            if endpoint:
                lines.append(endpoint)
            if inputs:
                lines.append(f'    inputs:  {inputs}')
            if outputs:
                lines.append(f'    outputs: {outputs}')
        lines.append('')

    if ctx['screens']:
        lines.append('Admin screens in the backend spec (these are internal/operator screens — do NOT mirror')
        lines.append('them in the design spec; the design spec is for the customer-facing website only):')
        for s in ctx['screens']:
            if s['kind'] == 'form':
                fields = ', '.join(f'{f["name"]} ({f["widget"]})' for f in s.get('fields', []))
                lines.append(f'  {s["name"]}  [form → {s["flow"]}]  fields: {fields}')
            else:
                cols = ', '.join(c['name'] for c in s.get('columns', []))
                lines.append(f'  {s["name"]}  [list of {s["entity"]}]  columns: {cols}')
        lines.append('')

    return '\n'.join(lines)
