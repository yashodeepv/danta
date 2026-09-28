"""graph.py - A flow: one trigger, typed steps, labelled edges.

The step kinds are the fixed catalog the flow encoder classifies into:

    kind       does                                     outgoing edges
    ---------  ---------------------------------------  -------------------------
    trigger    starts the flow; payload bound as input  next
    call       calls a declared service operation       next, error?
    query      reads the records of an entity           next
    publish    sends a message (or each of a list)      next
               to a topic
    compute    names values: the step's business logic  next
    validate   stops the flow unless a rule holds       next, error?
    branch     picks a path on a condition              true, false
    parallel   runs every branch, then the join step    branch x2+
    join       where parallel branches meet             next
    persist    writes a record of a declared entity     next
    notify     sends a message on a channel             next
    end        finishes, ok or error, with a response   (none)

`?` marks an optional edge. A call or validate with no error edge fails the
whole flow when it fails.

What each step makes available to later steps, by name:

    trigger    input      -> the payload record
    call       <step id>  -> the operation's output record (not on its error edge)
    query      <step id>  -> the list of matching records
    compute    <step id>  -> a record of the names it assigns

Everything else produces nothing. A value is usable at a step only if it is
produced on EVERY path into that step -- except at a join, where all parallel
branches have run, so their outputs combine.

Every step carries `title` (what the flowchart box shows) and `intent` (the
English the user wrote for it -- the input the logic model reads).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from danta.ir2.types import RecordT

MODES = ('sync', 'async')
SOURCES = ('http', 'event', 'schedule', 'topic')
CHANNELS = ('email', 'sms', 'slack', 'webhook')
PERSIST_OPS = ('create', 'update', 'delete')
END_STATUS = ('ok', 'error')

# kind -> {edge label: (min, max)}; None = unbounded
EDGES = {
    'trigger':  {'next': (1, 1)},
    'call':     {'next': (1, 1), 'error': (0, 1)},
    'compute':  {'next': (1, 1)},
    'validate': {'next': (1, 1), 'error': (0, 1)},
    'branch':   {'true': (1, 1), 'false': (1, 1)},
    'parallel': {'branch': (2, None)},
    'join':     {'next': (1, 1)},
    'persist':  {'next': (1, 1)},
    'notify':   {'next': (1, 1)},
    'query':    {'next': (1, 1)},
    'publish':  {'next': (1, 1)},
    'end':      {},
}
KINDS = tuple(EDGES)


@dataclass(kw_only=True)
class Step:
    id: str
    title: str = ''
    intent: str = ''
    kind = None


@dataclass(kw_only=True)
class Trigger(Step):
    kind = 'trigger'
    source: str                     # http event schedule topic
    config: Dict[str, str]          # http: method, path   event: name   schedule: cron   topic: name
    payload: RecordT


@dataclass(kw_only=True)
class Call(Step):
    kind = 'call'
    service: str
    op: str
    args: Dict[str, object]         # parameter -> expression
    retries: int = 0                # extra attempts after the first failure


@dataclass(kw_only=True)
class Compute(Step):
    kind = 'compute'
    assign: List[Tuple[str, object]]   # in order; later ones may use earlier ones


@dataclass(kw_only=True)
class Validate(Step):
    kind = 'validate'
    rule: object                    # bool expression that must hold
    message: str


@dataclass(kw_only=True)
class Branch(Step):
    kind = 'branch'
    cond: object


@dataclass(kw_only=True)
class Parallel(Step):
    kind = 'parallel'
    join: str                       # id of the join step the branches meet at


@dataclass(kw_only=True)
class Join(Step):
    kind = 'join'


@dataclass(kw_only=True)
class Persist(Step):
    kind = 'persist'
    entity: str
    op: str                         # create update delete
    data: Dict[str, object]         # field -> expression


@dataclass(kw_only=True)
class Notify(Step):
    kind = 'notify'
    channel: str
    to: object                      # str expression
    message: object                 # str expression


@dataclass(kw_only=True)
class Query(Step):
    """Read the records of an entity whose fields equal the given values (all
    of them when `where` is empty), in the order they were stored."""
    kind = 'query'
    entity: str
    where: Dict[str, object] = field(default_factory=dict)    # field -> expression


@dataclass(kw_only=True)
class Publish(Step):
    """Send a message to a topic: one record built from `message`, or -- with
    `each` -- every element of a list of records, one message apiece."""
    kind = 'publish'
    topic: str
    message: Optional[Dict[str, object]] = None     # field -> expression
    each: Optional[object] = None                   # list-of-records expression


@dataclass(kw_only=True)
class End(Step):
    kind = 'end'
    status: str = 'ok'
    response: Optional[Dict[str, object]] = None

    def message(self):
        """What a run that stops here reports as its error: the error message
        (`reason`) when it is a literal, else the step's title."""
        reason = (self.response or {}).get('reason')
        text = getattr(reason, 'v', None)
        if isinstance(text, str):
            return text
        return self.title or 'stopped with an error'


STEP_CLASSES = {c.kind: c for c in (Trigger, Call, Compute, Validate, Branch,
                                    Parallel, Join, Persist, Notify, Query, Publish, End)}


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    on: str = 'next'


@dataclass(frozen=True)
class Signature:
    input: RecordT
    output: RecordT


@dataclass
class Flow:
    name: str
    mode: str                                   # sync async
    steps: List[Step]
    edges: List[Edge]
    services: Dict[str, Dict[str, Signature]] = field(default_factory=dict)
    entities: Dict[str, RecordT] = field(default_factory=dict)
    title: str = ''
    intent: str = ''                            # the whole request, in English

    def step(self, sid) -> Optional[Step]:
        for s in self.steps:
            if s.id == sid:
                return s
        return None

    def out_edges(self, sid) -> List[Edge]:
        return [e for e in self.edges if e.src == sid]

    def in_edges(self, sid) -> List[Edge]:
        return [e for e in self.edges if e.dst == sid]

    def next(self, sid, on='next') -> Optional[str]:
        for e in self.out_edges(sid):
            if e.on == on:
                return e.dst
        return None

    def trigger(self) -> Optional[Trigger]:
        for s in self.steps:
            if isinstance(s, Trigger):
                return s
        return None
