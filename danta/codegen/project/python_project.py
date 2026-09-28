"""python_project.py - A system -> a complete Python project (standard library only).

    <system>/
      pyproject.toml   README.md
      src/<pkg>/  runtime.py models.py ports.py app.py __main__.py
                  flows/  one module per flow, and a registry
                  triggers/  http.py events.py schedule.py
                  adapters/  memory.py  (in-memory store, printing notifier, fake services)
      tests/      one test module per flow, one test per scenario
"""

import json
import re

from danta.codegen.project.common import (camel, collect_types, data_entities, fake_outputs, outline, py_type, snake,
                                         trigger_line)
from danta.codegen.openapi import asyncapi, openapi
from danta.codegen.project import deploy, frontend, infra
from danta.codegen.python import RUNTIME, flow_function, _machine, var
from danta.codegen.structure import Unstructured
from danta.ir2.types import BOOL, INT, STR, ListT, RecordT

HELPERS = ['CallFailed', 'Failed', 'call', 'failed', 'ok', '_div', '_mod', '_fmt', '_idx', '_reduce', '_s32', '_M']

EXECUTE = '''

def execute(flow, request, io):
    """Run one flow function and turn failures into an error result."""
    try:
        return flow(request, io)
    except Failed as e:
        return failed(str(e))
    except _Fault as e:
        return failed(f'{io.at}: {e}')
'''

CRON = '''

def cron_matches(cron, when):
    """Does a 5-field cron expression (minute hour day month weekday) match `when`?
    Supports *, */n, a-b, a,b and plain numbers; weekday 0 is Sunday."""
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError(f'expected 5 cron fields, got {cron!r}')
    values = [when.minute, when.hour, when.day, when.month, (when.weekday() + 1) % 7]
    return all(_field_matches(f, v) for f, v in zip(fields, values))


def _field_matches(field, value):
    for part in field.split(','):
        step = 1
        if '/' in part:
            part, step = part.split('/')
            step = int(step)
        if part == '*':
            if value % step == 0:
                return True
            continue
        lo, _, hi = part.partition('-')
        lo, hi = int(lo), int(hi or lo)
        if lo <= value <= hi and (value - lo) % step == 0:
            return True
    return False
'''


def _default(t):
    if t == INT:
        return '0'
    if t == BOOL:
        return 'False'
    if t == STR:
        return "''"
    if isinstance(t, ListT):
        return '[]'
    if isinstance(t, RecordT):
        return '{' + ', '.join(f'{n!r}: {_default(ft)}' for n, ft in t.fields) + '}'
    return 'None'


def _models(system, namer):
    out = ['"""Data shapes: entities, flow inputs and service contracts (plain dicts at runtime)."""',
           '', 'from typing import List, TypedDict', '']
    for name, rec in namer.defs:
        out += ['', f'class {name}(TypedDict):']
        out += [f'    {n}: {py_type(t, namer)}' for n, t in rec.fields] or ['    pass']
    return '\n'.join(out) + '\n'


def _ports(system, namer):
    out = ['"""The outside world, as interfaces. Implement these to connect real systems."""', '',
           'from typing import Protocol', '', 'from .models import *  # noqa: F401,F403',
           'from .runtime import ServiceError', '']
    for s, ops in sorted(system.services.items()):
        out += ['', f'class {camel(s)}(Protocol):', f'    """The {s} service. Raise ServiceError when a call fails."""']
        for op, sig in ops.items():
            params = ', '.join(f'{n}: {py_type(t, namer)}' for n, t in sig.input.fields)
            out.append(f'    def {op}(self{", " if params else ""}{params}) -> {namer.names[sig.output]}: ...')
    out += ['''

class Store(Protocol):
    def __call__(self, entity: str, op: str, data: dict) -> None:
        """op is 'create', 'update' or 'delete'; update and delete match the entity's key field."""


class Notifier(Protocol):
    def __call__(self, channel: str, to: str, message: str) -> None:
        """channel is 'email', 'slack', 'sms' or 'webhook'."""


class Services:
    """Routes the flows' calls to your service objects:

        Services(payments=MyPayments(), inventory=MyInventory())
    """

    def __init__(self, **impls):
        self.impls = impls

    def __call__(self, service, op, args, step=None):
        impl = self.impls.get(service)
        if impl is None:
            raise ServiceError(f'no implementation for service {service}')
        return getattr(impl, op)(**args)
''']
    return '\n'.join(out)


def _memory(system, namer):
    keys = {e: rec.fields[0][0] for e, rec in system.entities.items()}
    out = ['"""In-memory adapters: run and try the flows before real systems are connected."""', '',
           'from ..ports import Services', '', '',
           f'KEYS = {keys!r}', '', '',
           '''class MemoryStore:
    """Keeps records in a dict of lists, one list per entity."""

    def __init__(self):
        self.records = {}

    def __call__(self, entity, op, data):
        rows = self.records.setdefault(entity, [])
        key = KEYS.get(entity)
        if op == 'create':
            rows.append(dict(data))
            return
        matching = [r for r in rows if r.get(key) == data.get(key)]
        for r in matching:
            rows.remove(r)
        if op == 'update':
            rows.append(dict(data))

    def query(self, entity, where):
        """The records whose fields equal `where`, in stored order."""
        return [dict(r) for r in self.records.get(entity, [])
                if all(r.get(k) == v for k, v in where.items())]


class LocalTopics:
    """An in-process message bus: publishing hands the message to every flow
    subscribed to the topic, right away. Replace with a real broker to go async."""

    def __init__(self):
        self.published = []
        self.deliver = None                   # set by app.py: deliver(topic, message)

    def __call__(self, topic, message):
        self.published.append((topic, message))
        if self.deliver:
            self.deliver(topic, message)


class PrintNotifier:
    """Prints messages and keeps them in .sent."""

    def __init__(self, quiet=False):
        self.sent, self.quiet = [], quiet

    def __call__(self, channel, to, message):
        self.sent.append((channel, to, message))
        if not self.quiet:
            print(f'[{channel} -> {to}] {message}')
''']
    values = fake_outputs(system)
    for s, ops in sorted(system.services.items()):
        out += ['', '', f'class Fake{camel(s)}:',
                f'    """Stands in for the {s} service: always succeeds, with the values of the passing test run."""']
        for op, sig in ops.items():
            params = ', '.join(n for n, _ in sig.input.fields)
            out += ['', f'    def {op}(self{", " if params else ""}{params}):',
                    f'        return {values[(s, op)]!r}']
    fakes = ', '.join(f'{s}=Fake{camel(s)}()' for s in sorted(system.services))
    out += ['', '', 'def fake_services():', f'    return Services({fakes})', '']
    return '\n'.join(out)


def _flow_module(flow, pkg):
    try:
        code = flow_function(flow, var(flow.name))
        form = 'structured'
    except Unstructured:
        code = _machine(flow)
        form = 'state machine'
    used = [h for h in HELPERS if re.search(rf'(?<![\w.]){re.escape(h)}\b', code)]
    head = [f'"""{flow.name}: {flow.intent or "generated flow"}',
            '', f'Trigger: {trigger_line(flow)}   Mode: {flow.mode}   Form: {form}',
            'Generated by Danta from IR2. Regenerate rather than edit by hand."""', '']
    if used:
        head.append(f'from ..runtime import {", ".join(used)}')
    return '\n'.join(head) + '\n\n\n' + code + '\n'


def _triggers_meta(system):
    meta = {}
    for f in system.flows:
        t = f.trigger()
        meta[f.name] = {'source': t.source, 'mode': f.mode, **t.config}
    return meta


def _flows_init(system):
    lines = ['"""Every flow, by name, and what triggers it."""', '']
    for f in system.flows:
        lines.append(f'from .{snake(f.name)} import {var(f.name)}')
    lines += ['', 'FLOWS = {'] + [f'    {f.name!r}: {var(f.name)},' for f in system.flows] + ['}', '']
    lines.append('TRIGGERS = ' + json.dumps(_triggers_meta(system), indent=4))
    return '\n'.join(lines) + '\n'


APP = '''"""Wiring: build an IO from adapters, and run a flow by name.

Adapters are chosen from config (environment variables): in memory by default,
MongoDB / RabbitMQ / SMTP when configured. They are shared by every run, so
records saved by one flow are there for the next, and messages published by
one flow reach the flows listening.
"""

import logging

from . import config
from .adapters.memory import KEYS, LocalTopics, MemoryStore, PrintNotifier, fake_services
from .flows import FLOWS, TRIGGERS
from .runtime import IO, execute

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')


def _store():
    if config.STORE == 'mongo':
        from .adapters.real import MongoStore

        return MongoStore(config.MONGO_URL, config.MONGO_DB, KEYS)
    return MemoryStore()


def _topics():
    if config.BROKER == 'rabbitmq':
        from .adapters.real import RabbitTopics

        return RabbitTopics(config.RABBITMQ_URL, config.SERVICE)
    return LocalTopics()


def _notifier():
    if config.NOTIFY == 'smtp':
        from .adapters.real import SmtpNotifier

        return SmtpNotifier(config.SMTP_HOST, config.SMTP_PORT, config.SMTP_FROM, config.SMTP_USER, config.SMTP_PASSWORD)
    return PrintNotifier()


STORE = _store()
NOTIFIER = _notifier()
TOPICS = _topics()
SUBSCRIBERS = {}
for _name, _t in TRIGGERS.items():
    if _t['source'] == 'topic':
        SUBSCRIBERS.setdefault(_t['name'], []).append(_name)


def make_io(services=None, store=None, notify=None, query=None, publish=None):
    """Real systems go here: make_io(services=Services(payments=...), store=..., notify=...)."""
    store = store or STORE
    return IO(services or fake_services(), store, notify or NOTIFIER,
              query or getattr(store, 'query', None), publish or TOPICS)


def run_flow(name, request, io=None):
    return execute(FLOWS[name], request, io or make_io())


def deliver(topic, message):
    """Run every flow subscribed to `topic` with the message as its input."""
    return {name: run_flow(name, dict(message)) for name in SUBSCRIBERS.get(topic, [])}


def start_consumers():
    """With a real broker, consume the subscribed topics in the background."""
    if SUBSCRIBERS and hasattr(TOPICS, 'consume'):
        TOPICS.consume(SUBSCRIBERS, lambda name, message: run_flow(name, dict(message)))


if isinstance(TOPICS, LocalTopics):
    TOPICS.deliver = deliver
'''

CONFIG = '''"""Settings, from environment variables. The defaults run everything in memory."""

import os

STORE = os.environ.get('STORE', 'memory')              # memory | mongo
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
MONGO_DB = os.environ.get('MONGO_DB', '{pkg}')
BROKER = os.environ.get('BROKER', 'memory')            # memory | rabbitmq
RABBITMQ_URL = os.environ.get('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672')
NOTIFY = os.environ.get('NOTIFY', 'print')             # print | smtp
SMTP_HOST = os.environ.get('SMTP_HOST', 'localhost')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '1025'))
SMTP_FROM = os.environ.get('SMTP_FROM', '{name}@example.com')
SMTP_USER = os.environ.get('SMTP_USER', '')                # set both for a real relay (STARTTLS + login)
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
ADMIN_API = os.environ.get('ADMIN_API', '0') == '1'
# 0 on replicas that must not run the scheduled flows (exactly one instance should)
RUN_SCHEDULER = os.environ.get('RUN_SCHEDULER', '1') != '0'
SERVICE = '{name}'
'''

REAL = '''"""Adapters for real infrastructure: MongoDB, RabbitMQ and SMTP (chosen in app.py from config)."""

import json
import logging
import smtplib
import threading
import time
from email.message import EmailMessage

log = logging.getLogger(__name__)


class MongoStore:
    """Records in MongoDB, one collection per entity. Updates and deletes match the entity's
    key field; queries return records in the order they were stored."""

    def __init__(self, url, database, keys):
        from pymongo import MongoClient

        self.db = MongoClient(url)[database]
        self.keys = keys

    def __call__(self, entity, op, data):
        collection = self.db[entity]
        key = self.keys[entity]
        if op != 'create':
            collection.delete_many({key: data[key]})
        if op != 'delete':
            collection.insert_one(dict(data))

    def query(self, entity, where):
        rows = self.db[entity].find(dict(where)).sort('_id', 1)
        return [{k: v for k, v in r.items() if k != '_id'} for r in rows]


class RabbitTopics:
    """Topics on a RabbitMQ topic exchange. Each subscribed flow has its own durable queue,
    so every flow gets every message and several app instances share the work."""

    EXCHANGE = 'flows'

    def __init__(self, url, service):
        import pika

        self.pika, self.url, self.service = pika, url, service
        self._lock = threading.Lock()
        self._channel = None

    def _connect(self, attempts=30):
        for i in range(attempts):
            try:
                connection = self.pika.BlockingConnection(self.pika.URLParameters(self.url))
                channel = connection.channel()
                channel.exchange_declare(self.EXCHANGE, exchange_type='topic', durable=True)
                return channel
            except self.pika.exceptions.AMQPConnectionError:
                time.sleep(2)
        raise RuntimeError(f'cannot reach RabbitMQ at {self.url}')

    def __call__(self, topic, message):
        body = json.dumps(message).encode()
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._channel is None or self._channel.is_closed:
                        self._channel = self._connect()
                    self._channel.basic_publish(
                        self.EXCHANGE, topic, body,
                        properties=self.pika.BasicProperties(content_type='application/json', delivery_mode=2))
                    return
                except self.pika.exceptions.AMQPError:
                    self._channel = None
                    if attempt == 2:
                        raise

    def consume(self, subscribers, handle):
        """Run handle(flow_name, message) for every message on the subscribed topics, in a thread."""

        def work():
            channel = self._connect()
            channel.basic_qos(prefetch_count=1)
            for topic, names in subscribers.items():
                for name in names:
                    queue = f'{self.service}.{name}'
                    channel.queue_declare(queue, durable=True)
                    channel.queue_bind(queue, self.EXCHANGE, routing_key=topic)

                    def on_message(ch, method, props, body, name=name):
                        try:
                            handle(name, json.loads(body))
                        except Exception:
                            log.exception('flow %s failed on a message', name)
                        ch.basic_ack(method.delivery_tag)

                    channel.basic_consume(queue, on_message)
            log.info('consuming %s', ', '.join(subscribers))
            channel.start_consuming()

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread


class SmtpNotifier:
    """Sends email over SMTP (Mailpit catches it locally); other channels are logged.
    With a user and password (a real relay) it upgrades to TLS and logs in."""

    def __init__(self, host, port, sender, user='', password=''):
        self.host, self.port, self.sender = host, port, sender
        self.user, self.password = user, password

    def __call__(self, channel, to, message):
        if channel != 'email':
            log.info('[%s -> %s] %s', channel, to, message)
            return
        mail = EmailMessage()
        mail['From'], mail['To'] = self.sender, to
        mail['Subject'] = message[:78]
        mail.set_content(message)
        with smtplib.SMTP(self.host, self.port) as smtp:
            if self.user:
                smtp.starttls()
                smtp.login(self.user, self.password)
            smtp.send_message(mail)
'''

DOCKERFILE = '''FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["python", "-m", "{pkg}", "serve"]
'''

API = '''"""HTTP API (FastAPI): one endpoint per HTTP-triggered flow.

Swagger UI is at /docs and the OpenAPI document at /openapi.json. The document
is the one generated from the spec (openapi.json), not inferred from this code,
so its request and response schemas are exact.
"""

import json
import threading
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from . import config
from .app import STORE, run_flow
from .flows import FLOWS, TRIGGERS

OPENAPI = json.loads((Path(__file__).parent / 'openapi.json').read_text())

app = FastAPI(title=OPENAPI['info']['title'], version=OPENAPI['info']['version'])
app.openapi = lambda: OPENAPI


def _endpoint(name, mode):
    def handler(body: dict = Body(default=None)):
        request = body or {}
        if mode == 'async':
            threading.Thread(target=run_flow, args=(name, request), daemon=True).start()
            return JSONResponse({'accepted': True}, status_code=202)
        try:
            result = run_flow(name, request)
        except (KeyError, TypeError) as e:
            return JSONResponse({'error': f'missing or malformed field: {e}'}, status_code=400)
        if result['status'] == 'ok':
            return JSONResponse(result['response'] or {}, status_code=200)
        return JSONResponse({'error': result['error'], **(result['response'] or {})}, status_code=422)

    handler.__name__ = name
    return handler


for _name, _t in TRIGGERS.items():
    if _t['source'] == 'http':
        app.add_api_route(_t['path'], _endpoint(_name, _t['mode']), methods=[_t['method']])

# The records the frontend's list screens read: GET /data/<entity>?field=value&...
DATA = {DATA}


@app.get('/data/{entity}')
def read_records(entity: str, request: Request):
    fields = DATA.get(entity)
    if fields is None:
        return JSONResponse({'error': f'no screen lists {entity}'}, status_code=404)
    where = {}
    for key, raw in request.query_params.items():
        if key not in fields:
            return JSONResponse({'error': f'{entity} has no field {key}'}, status_code=400)
        try:
            where[key] = int(raw) if fields[key] == 'int' else raw == 'true' if fields[key] == 'bool' else raw
        except ValueError:
            return JSONResponse({'error': f'{key} must be a whole number'}, status_code=400)
    return STORE.query(entity, where)


if config.ADMIN_API:
    # Local testing only (ADMIN_API=1): run any flow, and read or seed records.

    @app.post('/admin/flows/{name}')
    def admin_run(name: str, body: dict = Body(default=None)):
        if name not in FLOWS:
            return JSONResponse({'error': f'unknown flow {name}'}, status_code=404)
        return run_flow(name, body or {})

    @app.get('/admin/store/{entity}')
    def admin_records(entity: str):
        return STORE.query(entity, {})

    @app.post('/admin/store/{entity}')
    def admin_seed(entity: str, body: dict = Body(...)):
        STORE(entity, 'create', body)
        return {'created': True}
'''

EVENTS = '''"""Event entry points: publish(event_name, payload) runs the flow listening for it."""

from ..app import run_flow
from ..flows import TRIGGERS

EVENTS = {t['name']: name for name, t in TRIGGERS.items() if t['source'] == 'event'}


def publish(event, payload, io=None):
    name = EVENTS.get(event)
    if name is None:
        raise KeyError(f'no flow listens for event {event!r}')
    return run_flow(name, payload, io)
'''

SCHEDULE = '''"""Scheduled flows: run_due() runs every flow whose cron matches the current minute."""

import datetime
import time

from ..app import run_flow
from ..flows import FLOWS, TRIGGERS
from ..runtime import cron_matches

SCHEDULES = [(t['cron'], name) for name, t in TRIGGERS.items() if t['source'] == 'schedule']


def payload_for(name, when):
    """The payload a scheduled run receives. Edit to suit: by default every str
    field gets today's date and every int field 0."""
    return PAYLOADS[name](when)


PAYLOADS = {PAYLOAD_BUILDERS}


def run_due(when=None, io=None):
    when = when or datetime.datetime.now()
    return {name: run_flow(name, payload_for(name, when), io)
            for cron, name in SCHEDULES if cron_matches(cron, when)}


def loop(io_factory=None):
    last = None
    while True:
        now = datetime.datetime.now().replace(second=0, microsecond=0)
        if now != last:
            last = now
            for name, result in run_due(now, io_factory() if io_factory else None).items():
                print(f'{now:%Y-%m-%d %H:%M} {name}: {result["status"]}')
        time.sleep(5)
'''

MAIN = '''"""python -m {pkg} <command>

    serve [--port 8000]      the HTTP API (Swagger UI at /docs), plus the scheduler
    run FLOW 'JSON'          run one flow with a JSON payload
    event NAME 'JSON'        publish an event
    tick                     run the scheduled flows due this minute
    publish TOPIC 'JSON'     publish a message to a topic
"""

import argparse
import json
import os
import sys
import threading

from . import config
from .app import TOPICS, run_flow
from .flows import FLOWS
from .triggers import events, schedule


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m {pkg}', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['serve', 'run', 'event', 'tick', 'publish'])
    ap.add_argument('name', nargs='?')
    ap.add_argument('payload', nargs='?', default='{{}}')
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8000)))
    a = ap.parse_args(argv)
    if a.command == 'serve':
        if schedule.SCHEDULES and config.RUN_SCHEDULER:
            threading.Thread(target=schedule.loop, daemon=True).start()
        import uvicorn

        from .api import app
        from .app import start_consumers

        start_consumers()
        uvicorn.run(app, host=os.environ.get('HOST', '127.0.0.1'), port=a.port)
    elif a.command == 'run':
        if a.name not in FLOWS:
            sys.exit(f'unknown flow {{a.name!r}} (flows: {{", ".join(FLOWS)}})')
        print(json.dumps(run_flow(a.name, json.loads(a.payload)), indent=2))
    elif a.command == 'event':
        print(json.dumps(events.publish(a.name, json.loads(a.payload)), indent=2))
    elif a.command == 'publish':
        TOPICS(a.name, json.loads(a.payload))
        print(f'published to {{a.name}}')
    else:
        print(json.dumps(schedule.run_due(), indent=2))


if __name__ == '__main__':
    main()
'''

TEST = '''"""{flow}: every generated scenario, replayed. Generated from the reference simulator."""

import json
import unittest

from {pkg}.flows.{module} import {fn}
from {pkg}.runtime import IO, ServiceError, execute

SCENARIOS = json.loads(r\'\'\'{scenarios}\'\'\')
KEYS = {keys}


def replay(scenario):
    mocks, effects, attempts = scenario.get('mocks', {{}}), [], {{}}
    rows = json.loads(json.dumps(scenario.get('store') or {{}}))

    def services(service, op, args, step=None):
        n = attempts[step] = attempts.get(step, 0) + 1
        outcomes = mocks[step] if isinstance(mocks[step], list) else [mocks[step]]
        outcome = outcomes[min(n, len(outcomes)) - 1]
        effects.append(f'call {{service}}.{{op}} #{{n}}')
        if 'ok' in outcome:
            return json.loads(json.dumps(outcome['ok']))
        raise ServiceError(outcome['error'])

    def store(entity, op, data):
        effects.append(f'persist {{entity}}.{{op}}')
        table = rows.setdefault(entity, [])
        if op == 'create':
            table.append(dict(data))
        else:
            table[:] = [r for r in table if r.get(KEYS[entity]) != data.get(KEYS[entity])]
            if op == 'update':
                table.append(dict(data))

    def query(entity, where):
        return [dict(r) for r in rows.get(entity, []) if all(r.get(k) == v for k, v in where.items())]

    def publish(topic, message):
        text = json.dumps(message, separators=(',', ':'), ensure_ascii=False)
        effects.append(f'publish {{topic}} {{text}}')

    def notify(channel, to, message):
        effects.append(f'notify {{channel}} {{to}}: {{message}}')

    io = IO(services, store, notify, query, publish)
    result = execute({fn}, json.loads(json.dumps(scenario['input'])), io)
    return result, effects


class Test{cls}(unittest.TestCase):
    pass


def _make(name):
    def test(self):
        scenario = SCENARIOS[name]
        result, effects = replay(scenario)
        want = scenario['expect']
        self.assertEqual(result['status'], want['status'])
        self.assertEqual(result['response'], want.get('response'))
        self.assertEqual(effects, want['effects'])
    return test


for _name in SCENARIOS:
    setattr(Test{cls}, f'test_{{_name}}', _make(_name))


if __name__ == '__main__':
    unittest.main()
'''


API_TEST = '''"""The HTTP API: the OpenAPI document and Swagger UI are served, and every
HTTP-triggered flow answers (with the in-memory stand-ins in place)."""

import json
import unittest

from fastapi.testclient import TestClient

from {pkg}.api import app

CLIENT = TestClient(app)
CALLS = json.loads(r\'\'\'{calls}\'\'\')


class TestApi(unittest.TestCase):
    def test_openapi_document(self):
        r = CLIENT.get('/openapi.json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['info']['title'], {title!r})

    def test_swagger_ui(self):
        self.assertEqual(CLIENT.get('/docs').status_code, 200)

    def test_every_endpoint_answers(self):
        for call in CALLS:
            with self.subTest(path=call['path']):
                r = CLIENT.request(call['method'], call['path'], json=call['body'])
                self.assertIn(r.status_code, call['expect'])


if __name__ == '__main__':
    unittest.main()
'''


def _api_calls(system):
    calls = []
    for f in system.flows:
        t = f.trigger()
        scenarios = system.scenarios.get(f.name, {})
        if t.source != 'http' or not scenarios:
            continue
        calls.append({'method': t.config['method'], 'path': t.config['path'],
                      'body': next(iter(scenarios.values()))['input'],
                      'expect': [202] if f.mode == 'async' else [200, 422]})
    return calls


def _payload_builders(system):
    items = []
    for f in system.flows:
        t = f.trigger()
        if t.source != 'schedule':
            continue
        fields = []
        for n, ft in t.payload.fields:
            v = "when.strftime('%Y-%m-%d')" if ft == STR else _default(ft)
            fields.append(f'{n!r}: {v}')
        items.append(f"\n    {f.name!r}: lambda when: {{{', '.join(fields)}}},")
    return '{' + ''.join(items) + ('\n}' if items else '}')


def _readme(system, pkg, verified=None):
    lines = [f'# {system.name}', '']
    if system.description:
        lines += [system.description, '']
    lines += ['Generated by Danta from a Danta Spec. Every flow was verified against the',
              'reference simulator; `tests/` replays those scenarios, so keep them passing when you',
              'edit.', '', '## Flows', '']
    for f in system.flows:
        lines += [f'### {f.name}', '', f'`{trigger_line(f)}`, {f.mode}.', '']
        if f.intent:
            lines += [f.intent, '']
        lines += outline(f) + ['']
    lines += ['## Run', '', 'From this folder:', '', '```bash', 'pip install -e .',
              f'PYTHONPATH=src python -m unittest discover -s tests',
              f'PYTHONPATH=src python -m {pkg} serve      # http://127.0.0.1:8000/docs',
              f"PYTHONPATH=src python -m {pkg} run {system.flows[0].name} '{{...}}'", '```', '',
              *infra.readme_section(system, 8000, f'`PYTHONPATH=src python -m {pkg} serve`.'),
              *frontend.readme_section(system, 8000),
              '## API and topics', '',
              '- **HTTP:** Swagger UI at `/docs`; the OpenAPI document is `src/' + pkg + '/openapi.json`,',
              '  generated from the spec.',
              '- **Topics:** `docs/asyncapi.json` lists every topic, who publishes to it and who consumes it.', '',
              '## Connect real systems', '',
              f'Implement the interfaces in `src/{pkg}/ports.py` and pass them to `make_io`:', '', '```python',
              f'from {pkg}.app import make_io, run_flow', f'from {pkg}.ports import Services', '',
              'io = make_io(services=Services(' + ', '.join(f'{s}=My{camel(s)}()' for s in sorted(system.services))
              + '),', '             store=my_store, notify=my_notifier)',
              f'run_flow({system.flows[0].name!r}, payload, io)', '```', '',
              'Parallel steps run one after another, in the order written. Integers are signed 32-bit',
              '(money in cents) and wrap on overflow, exactly as in the spec.', '']
    return '\n'.join(lines)


def generate(system):
    """System -> {relative path: file content}."""
    pkg = snake(system.name)
    namer = collect_types(system)
    root = system.name
    files = {
        f'{root}/pyproject.toml': f'''[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "{system.name}"
version = "0.1.0"
description = "{(system.description or 'Generated by Danta').replace('"', "'")[:200]}"
requires-python = ">=3.9"
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "pymongo>=4.6",
    "pika>=1.3",
]

[project.optional-dependencies]
test = ["httpx>=0.27"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
"*" = ["openapi.json"]
''',
        f'{root}/README.md': _readme(system, pkg),
        f'{root}/src/{pkg}/__init__.py': f'"""{system.name} - generated by Danta."""\n\n__version__ = "0.1.0"\n',
        f'{root}/src/{pkg}/runtime.py': '"""Shared runtime for the generated flows: results, service calls, 32-bit arithmetic."""\n\n'
                                         + RUNTIME.strip() + '\n' + EXECUTE + CRON,
        f'{root}/src/{pkg}/models.py': _models(system, namer),
        f'{root}/src/{pkg}/ports.py': _ports(system, namer),
        f'{root}/src/{pkg}/app.py': APP,
        f'{root}/src/{pkg}/__main__.py': MAIN.replace('{pkg}', pkg).replace('{{', '{').replace('}}', '}'),
        f'{root}/src/{pkg}/flows/__init__.py': _flows_init(system),
        f'{root}/src/{pkg}/triggers/__init__.py': '"""What starts a flow besides HTTP (api.py): events and schedules."""\n',
        f'{root}/src/{pkg}/api.py': API.replace('{DATA}', repr(data_entities(system))),
        f'{root}/src/{pkg}/config.py': CONFIG.replace('{pkg}', pkg).replace('{name}', system.name),
        f'{root}/src/{pkg}/adapters/real.py': REAL,
        f'{root}/Dockerfile': DOCKERFILE.replace('{pkg}', pkg),
        f'{root}/.dockerignore': '.git\n__pycache__/\n*.pyc\n.venv/\ntests/\n',
        f'{root}/docker-compose.yml': infra.compose(system, 8000, 'python'),
        f'{root}/.env.example': infra.env_example(system, 8000),
        f'{root}/src/{pkg}/openapi.json': json.dumps(openapi(system), indent=2) + '\n',
        f'{root}/docs/asyncapi.json': json.dumps(asyncapi(system), indent=2) + '\n',
        f'{root}/tests/test_api.py': API_TEST.format(pkg=pkg, title=system.name,
                                                     calls=json.dumps(_api_calls(system), indent=1)),
        f'{root}/src/{pkg}/triggers/events.py': EVENTS,
        f'{root}/src/{pkg}/triggers/schedule.py': SCHEDULE.replace('{PAYLOAD_BUILDERS}', _payload_builders(system)),
        f'{root}/src/{pkg}/adapters/__init__.py': '"""Adapters: stand-ins for real systems."""\n',
        f'{root}/src/{pkg}/adapters/memory.py': _memory(system, namer),
        f'{root}/tests/__init__.py': '',
    }
    for f in system.flows:
        mod = snake(f.name)
        files[f'{root}/src/{pkg}/flows/{mod}.py'] = _flow_module(f, pkg)
        scenarios = system.scenarios.get(f.name, {})
        files[f'{root}/tests/test_{mod}.py'] = TEST.format(
            flow=f.name, pkg=pkg, module=mod, fn=var(f.name), cls=camel(f.name),
            scenarios=json.dumps(scenarios, indent=1),
            keys=repr({e: rec.fields[0][0] for e, rec in system.entities.items()}))
    files.update(frontend.generate_web(system, 8000))
    files.update({f'{root}/{k}': v for k, v in deploy.manifests(system, 8000, 'IMAGE').items()})
    return files
