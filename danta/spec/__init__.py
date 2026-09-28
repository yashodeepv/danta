"""spec - Danta Spec: the system specification language, and its compiler.

    LANGUAGE.md   the language reference (normative)
    examples/     example system specs
    document.py   text -> sections and a step tree, with line numbers
    text.py       splitting step text outside quotes, backquotes and brackets
    types.py      spec type syntax -> IR2 types
    values.py     value slots, names and templates -> IR2; the name resolver
    exact.py      exact expressions -> IR2
    compile.py    the whole document -> IR2 flows, or line-numbered errors

    danta check   flow/spec/examples/order_checkout.spec.md
    danta show    flow/spec/examples/order_checkout.spec.md
    danta compile flow/spec/examples/order_checkout.spec.md --out build/
"""

from danta.spec.compile import Compiled, Intent, compile_spec
from danta.spec.document import SpecError

__all__ = ['compile_spec', 'Compiled', 'Intent', 'SpecError']
