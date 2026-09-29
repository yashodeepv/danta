"""prompt.py - The text a user pastes into an LLM to get a Danta Spec back.

Assembled from LANGUAGE.md and an example spec at request time, so the
prompt can never drift from the grammar the compiler actually accepts.
"""

import os

SPEC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'spec')

INSTRUCTIONS = '''You are the analyst for Danta, a system that builds verified software
from a precise specification. Read the USE CASE at the end of this message and
write a complete system spec for it in Danta Spec 0.1, the language defined in
the LANGUAGE REFERENCE below.

Rules:
1. Reply with the spec only, inside a single ```markdown code block. The first
   line of the spec is exactly: Spec: danta/0.1
2. Declare every entity and service operation the flows use, with exact types.
   If the use case doesn't name them, choose clear snake_case names yourself.
3. Write every value as a name, a literal, a template, or an exact expression
   in backquotes. Do NOT write prose values: this installation has no logic
   model yet, so prose can't be compiled.
4. Money is an int in minor units (cents). There are no decimals.
5. Give every step a short [title] in the business's own words. Business
   people review the flowchart drawn from these titles; they never read the spec.
6. Resolve every ambiguity yourself with a sensible default, and state the
   defaults you chose in the flow's Intent: line.
7. Stay inside Danta Spec 0.1. If the use case needs something it can't
   express (steps inside a loop, timeouts), design the closest supported flow
   and explain the gap in a "> " comment line. For work over many records,
   use the batch pattern (section 7.13).
8. If people use the system through a web page, add ## Screen: sections
   (section 12): a form for each flow a person starts, and a list for each
   set of records a person works through, with actions for what they do to a
   row. A screen can only run HTTP flows, so give those flows HTTP triggers.
9. Check your spec against the validity rules in section 9 before replying:
   every name resolves, every call gives every parameter, every Save gives
   every field, Respond with appears only in sync flows, and every form lists
   every field of its flow's trigger.

Cross-language rules (the spec compiles to Python, JavaScript, AND Java):
10. Names must be snake_case. Never use reserved words as names:
    Python: class, type, list, id, input, print, filter, map, range, format, next
    Java: class, interface, package, import, new, default, extends, implements, final
    JavaScript: function, var, let, const, delete, yield, typeof, export
    Entity fields named "id" → use <entity>_id (e.g. order_id, user_id).
11. Use int for ALL whole numbers. Never float for currency; store money as cents.
12. Write expressions as valid Python syntax.
    Integer division: // not /   (e.g. `subtotal // 10`)
    Boolean literals: True / False   (codegen translates to true/false)
    String literals: double quotes only inside expressions ("gold", not \'gold\').
'''

# The example must follow rule 3, so its one prose value is swapped for the
# exact expression it stands for.
_EXAMPLE_FIX = ('   - enough_balance: days is at most balance, or kind is "sick"\n'
                '   > intent; expected: `days <= balance or kind == "sick"`\n',
                '   - enough_balance: `days <= balance or kind == "sick"`\n')


def example_spec():
    with open(os.path.join(SPEC_DIR, 'examples', 'leave_requests.spec.md')) as f:
        text = f.read()
    old, new = _EXAMPLE_FIX
    if old not in text:
        raise RuntimeError('the prompt example no longer matches leave_requests.spec.md')
    return text.replace(old, new)


def screens_example():
    with open(os.path.join(SPEC_DIR, 'examples', 'help_desk.spec.md')) as f:
        return f.read()


def examples():
    """The example specs Studio offers, the prompt's own example first."""
    import glob
    out = [{'name': 'leave_requests (all exact)', 'text': example_spec()}]
    for path in sorted(glob.glob(os.path.join(SPEC_DIR, 'examples', '*.spec.md'))):
        with open(path) as f:
            text = f.read()
        name = os.path.basename(path)[:-len('.spec.md')]
        out.append({'name': name + (' (with screens: web app)' if '## Screen:' in text else ''), 'text': text})
    return out


def build_prompt():
    with open(os.path.join(SPEC_DIR, 'LANGUAGE.md')) as f:
        language = f.read()
    return (INSTRUCTIONS
            + '\n========== LANGUAGE REFERENCE ==========\n\n' + language
            + '\n========== EXAMPLE SPEC ==========\n\n```markdown\n' + example_spec() + '```\n'
            + '\n========== EXAMPLE SPEC WITH SCREENS ==========\n\n```markdown\n' + screens_example() + '```\n'
            + '\n========== USE CASE ==========\n\n')
