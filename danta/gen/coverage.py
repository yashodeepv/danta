"""coverage.py - Invent scenarios until every edge of a flow has been taken.

Random inputs from the catalog's value pools, and for each call a random
behaviour: succeed, fail every attempt (to reach the error edge), or fail
then succeed (to exercise retries). Each run goes through the simulator; a
run is kept as a scenario only if it takes an edge no earlier run took.

A flow whose edges cannot all be reached -- `name == "Ana"` followed by
`if name == "Raj"` -- is a flow nobody would write. `synthesize` reports the
coverage it managed, and the corpus builder drops anything short of full.

The scenarios double as the test suite for generated code: a backend must
reproduce every one of them.

Flows that query the store get a seeded store too: a few random records per
queried entity, some of them made to match each query's conditions (a literal,
or the same-named payload field), so both the found and the not-found paths
happen.
"""

from danta.ir2 import graph as g
from danta.ir2.expr import Bool, Const, Ref, Str
from danta.gen.values import random_value
from danta.sim import run, summary


def _mocks(rng, flow, cat):
    mocks = {}
    for s in flow.steps:
        if not isinstance(s, g.Call):
            continue
        out = flow.services[s.service][s.op].output
        ok = {'ok': random_value(rng, out, cat)}
        err = {'error': rng.choice(['timeout', 'unavailable', 'rejected'])}
        mode = rng.choices(['ok', 'fail', 'flaky'], [6, 3, 2 if s.retries else 0])[0]
        if mode == 'ok':
            mocks[s.id] = ok
        elif mode == 'fail':
            mocks[s.id] = err
        else:
            mocks[s.id] = [err] * rng.randint(1, s.retries) + [ok]
    return mocks


def _store(rng, flow, cat, payload):
    queries = [s for s in flow.steps if isinstance(s, g.Query)]
    if not queries:
        return None
    store = {}
    for q in queries:
        rec = flow.entities[q.entity]
        rows = store.setdefault(q.entity, [random_value(rng, rec, cat) for _ in range(rng.randint(0, 4))])
        for row in rows:
            if rng.random() < 0.6:
                for k, e in q.where.items():
                    if isinstance(e, (Const, Str, Bool)):
                        row[k] = e.v
                    elif isinstance(e, Ref) and e.path[0] == 'input' and len(e.path) == 2 and e.path[1] in payload:
                        row[k] = payload[e.path[1]]
    return store


def expectation(res):
    exp = {'status': res.status, 'path': res.path(),
           'effects': [summary(e) for e in res.effects]}
    if res.response is not None:
        exp['response'] = res.response
    if res.error:
        exp['error'] = res.error
    return exp


def synthesize(rng, flow, cat, tries=300):
    """Returns (scenarios, fraction of edges covered)."""
    trig = flow.trigger()
    want = {(e.src, e.dst, e.on) for e in flow.edges}
    covered, scenarios = set(), {}
    for _ in range(tries):
        payload = random_value(rng, trig.payload, cat)
        mocks = _mocks(rng, flow, cat)
        store = _store(rng, flow, cat, payload)
        res = run(flow, payload, mocks, store)
        new = set(res.edges) - covered
        if not new:
            continue
        covered |= new
        used = {s for s in mocks if s in res.path()}
        scenarios[f's{len(scenarios) + 1}'] = {
            'input': payload,
            'mocks': {s: m for s, m in mocks.items() if s in used},
            **({'store': store} if store else {}),
            'expect': expectation(res),
        }
        if covered >= want:
            break
    return scenarios, len(covered & want) / len(want)
