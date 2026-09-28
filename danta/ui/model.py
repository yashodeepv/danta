"""model.py - Screens: what the generated frontend shows, as data.

A system's screens are compiled from `## Screen:` sections (LANGUAGE.md §12)
and checked against its flows and entities, so every screen is backed by
the API: a form posts exactly its flow's trigger payload, a list reads an
entity's records, and a list action posts a whole payload built from a row.

    Screen(kind='form')   fields -> POST <flow path>, then a message and/or a screen
    Screen(kind='list')   columns of <entity> records (fixed filters), row actions

Widgets (form fields) and formats (list columns) are closed sets, each
valid for particular types; the compiler rejects a widget on the wrong type.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# widget -> the IR2 type names it can edit ('record list' = list of records)
WIDGETS = {
    'text': {'str'}, 'long text': {'str'}, 'email': {'str'}, 'date': {'str'}, 'choice': {'str', 'int'},
    'generated': {'str'}, 'number': {'int'}, 'money': {'int'}, 'checkbox': {'bool'},
    'list': {'str list', 'int list'}, 'rows': {'record list'},
}
DEFAULT_WIDGET = {'str': 'text', 'int': 'number', 'bool': 'checkbox', 'str list': 'list', 'int list': 'list'}
FORMATS = {'text': {'str', 'int'}, 'number': {'int'}, 'money': {'int'}, 'date': {'str'}, 'yes/no': {'bool'}}
DEFAULT_FORMAT = {'str': 'text', 'int': 'number', 'bool': 'yes/no'}


def label_of(name):
    return name.replace('_', ' ').capitalize()


@dataclass
class Field:
    name: str
    label: str
    widget: str
    type: str                                   # 'str', 'int', 'bool', 'str list', 'int list', 'record list'
    choices: List[Any] = field(default_factory=list)
    rows: List['Field'] = field(default_factory=list)       # sub-fields of a 'rows' widget


@dataclass
class Column:
    name: str
    label: str
    format: str


@dataclass
class Action:
    label: str
    flow: str
    method: str
    path: str
    payload: Dict[str, Tuple[str, Any]]         # payload field -> ('field', row field) | ('value', literal)


@dataclass
class Screen:
    name: str
    title: str
    kind: str                                   # 'form' | 'list'
    line: int = 0
    # form
    flow: str = ''
    method: str = ''
    path: str = ''
    fields: List[Field] = field(default_factory=list)
    submit: str = 'Submit'
    message: str = ''                           # shown after success; {response field} placeholders
    go_to: Optional[str] = None                 # screen to open after success
    is_async: bool = False
    # list
    entity: str = ''
    columns: List[Column] = field(default_factory=list)
    filters: Dict[str, Any] = field(default_factory=dict)
    actions: List[Action] = field(default_factory=list)
