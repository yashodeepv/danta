"""correct.py - Build a correction prompt from a spec + compilation errors.

Usage:
    from danta.gen.correct import build_correction_prompt
    prompt = build_correction_prompt(spec_text, build_result['errors'])
"""

# Maps SpecError rule names → plain-English guidance for the LLM
RULE_HINTS: dict[str, str] = {
    'syntax':          'Fix the formatting: check the section header, bullet style, or line structure.',
    'layout':          'A required section or property is missing (e.g. a Screen needs "Title:" and "Shows:").',
    'unique-names':    'Every flow, entity, service, and screen must have a unique name.',
    'known-type':      'Use only the built-in types: str, int, bool, and list of <type>.',
    'known-entity':    '"Shows: list of <entity>" or "Save <entity>" must name an entity declared in ## Entities.',
    'known-service':   '"Call <service>.<op>" must match a service declared in ## Services exactly.',
    'resolves':        'Every name used in a step must be declared: a field from the trigger, a constant, or a prior compute result.',
    'types':           'The expression type does not match what the step or field expects.',
    'respond-sync':    '"Respond with" is only allowed in sync flows (Mode: sync). Async flows stop without a response.',
    'sync-http':       'HTTP POST/PUT/DELETE triggers run sync by default. Remove "Mode: async" or change the trigger.',
    'parallel-branch': 'Each branch of "In parallel" must be exactly one step. No Stop, Respond, If, or nested In parallel.',
    'check':           'A semantic rule failed — re-read the step and check names, types, and structure.',
    'screen-kind':     'A form screen allows Title/Shows/Fields/Submit/After. A list screen allows Title/Shows/Columns/Filter/Actions.',
    'screen-flow':     '"Shows: form for <flow>" must name a real HTTP POST/PUT/DELETE flow in this spec.',
    'screen-fields':   'The Fields list must include every field in the flow trigger, no more, no less.',
    'screen-columns':  'A list screen must declare "Columns:" with at least one column.',
    'screen-after':    '"After: go to <screen>" must name a real screen. Message placeholders like {order_id} must appear in the flow response.',
    'screen-action':   'An action button\'s "with" clause must supply every field the target flow\'s trigger requires.',
    'screen-filter':   'A Filter field must exist on the entity and its value must match the field\'s type.',
    'widget-type':     'The widget and the field\'s type must be compatible. Check the widget name and the field type.',
}

_CROSS_LANGUAGE = """\
Cross-language rules (this spec compiles to Python, JavaScript, AND Java simultaneously):

Names
  - snake_case only for all flow, entity, service, and field names.
  - Never use these reserved words as names:
      Python   : class, type, list, id, input, print, filter, map, range, format, next, iter, open
      Java     : class, interface, package, import, new, default, extends, implements, instanceof, final
      JavaScript: function, var, let, const, delete, yield, typeof, instanceof, export, import
  - Entity fields named "id" → rename to "<entity>_id" (e.g. order_id, user_id).

Numbers
  - Use int for ALL whole numbers, including money (store as cents, never decimals).
  - Never use float for currency — it causes rounding bugs in all three targets.
  - Java int max is ~2.1 billion. For large IDs or aggregates, use int; the codegen will widen if needed.

Expressions
  - Write expressions as valid Python syntax — the Python codegen uses them verbatim.
  - Java and JS codegens translate from Python automatically.
  - Integer division: use // not /  (e.g. `subtotal // 10`, not `subtotal / 10`).
  - Boolean literals: True / False (Python capitalisation); codegen translates to true/false.
  - String literals inside expressions: double quotes only ("gold", not 'gold').
"""


def build_correction_prompt(spec: str, errors: list, *, attempt: int = 1, max_attempts: int = 3, user_note: str = '') -> str:
    """Return a prompt that asks the LLM to fix `spec` given `errors`.

    `errors` is the list returned by pipeline.build()['errors']:
    each item has .rule, .line, .message (SpecError) or may be a plain str.
    `user_note` is optional plain-text guidance from the user (e.g. "add a refund flow").
    """
    if not errors:
        return ''

    lines = []
    lines.append(f'Attempt {attempt} of {max_attempts}: the spec below has {len(errors)} error(s). Fix them.')
    if user_note.strip():
        lines.append('')
        lines.append(f'The user also asks: "{user_note.strip()}"')
    lines.append('')
    lines.append('Errors:')
    for e in errors:
        if isinstance(e, dict):
            rule = e.get('rule', '')
            loc = f'line {e["line"]}: ' if e.get('line') else ''
            msg = e.get('message', str(e))
        elif hasattr(e, 'rule'):
            rule, loc, msg = e.rule, (f'line {e.line}: ' if getattr(e, 'line', None) else ''), e.message
        else:
            lines.append(f'  {e}')
            continue
        hint = RULE_HINTS.get(rule, '')
        lines.append(f'  [{rule}]  {loc}{msg}')
        if hint:
            lines.append(f'           → {hint}')

    lines.append('')
    lines.append(_CROSS_LANGUAGE)
    lines.append('')
    lines.append('Return ONLY the corrected spec inside a single ```markdown code block. No explanation.')
    lines.append('')
    lines.append('Current spec:')
    lines.append('```markdown')
    lines.append(spec.strip())
    lines.append('```')

    return '\n'.join(lines)
