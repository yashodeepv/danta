"""javascript_project.py - A system -> a complete Node.js project (no dependencies).

    <system>/
      package.json   README.md
      src/  runtime.js models.js ports.js app.js main.js
            flows/  one module per flow, and index.js
            triggers/  http.js events.js schedule.js
            adapters/  memory.js
      test/ one test file per flow (node:test), one test per scenario
"""

import json
import re

from danta.codegen.javascript import RUNTIME, flow_code, var
from danta.codegen.openapi import asyncapi, openapi
from danta.codegen.project import deploy, frontend, infra
from danta.codegen.project.common import (camel, collect_types, data_entities, fake_outputs, js_type, outline, snake,
                                         trigger_line)
from danta.ir2.types import BOOL, INT, STR, ListT, RecordT

HELPERS = ['CallFailed', 'Failed', 'call', 'failed', 'ok', 'div', 'mod', 'fmt', 'idx', 'reduce', 'range', 's32']

EXECUTE = '''

/** Run one flow function and turn failures into an error result. */
export async function execute(flow, request, io) {
  try {
    return await flow(request, io);
  } catch (e) {
    if (e instanceof Failed) return failed(e.message);
    if (e instanceof Fault) return failed(`${io.at}: ${e.message}`);
    throw e;
  }
}

/** Does a 5-field cron expression (minute hour day month weekday) match `when`?
 *  Supports *, *\\/n, a-b, a,b and plain numbers; weekday 0 is Sunday. */
export function cronMatches(cron, when) {
  const fields = cron.trim().split(/\\s+/);
  if (fields.length !== 5) throw new Error(`expected 5 cron fields, got ${cron}`);
  const values = [when.getMinutes(), when.getHours(), when.getDate(), when.getMonth() + 1, when.getDay()];
  return fields.every((f, i) => fieldMatches(f, values[i]));
}

function fieldMatches(field, value) {
  return field.split(',').some((part) => {
    let step = 1;
    if (part.includes('/')) { [part, step] = part.split('/'); step = Number(step); }
    if (part === '*') return value % step === 0;
    const [lo, hi] = part.split('-').map(Number);
    const top = Number.isNaN(hi) || hi === undefined ? lo : hi;
    return value >= lo && value <= top && (value - lo) % step === 0;
  });
}
'''


def _default(t):
    if t == INT:
        return '0'
    if t == BOOL:
        return 'false'
    if t == STR:
        return "''"
    if isinstance(t, ListT):
        return '[]'
    if isinstance(t, RecordT):
        return '{ ' + ', '.join(f'{n}: {_default(ft)}' for n, ft in t.fields) + ' }'
    return 'null'


def _models(namer):
    out = ['// Data shapes: entities, flow inputs and service contracts (plain objects at runtime).', '']
    for name, rec in namer.defs:
        out.append('/**')
        out.append(f' * @typedef {{Object}} {name}')
        out += [f' * @property {{{js_type(t, namer)}}} {n}' for n, t in rec.fields]
        out.append(' */')
        out.append('')
    out.append('export {};')
    return '\n'.join(out) + '\n'


def _ports(system, namer):
    out = ["// The outside world, as interfaces. Implement these to connect real systems.",
           "import { ServiceError } from './runtime.js';", '']
    for s, ops in sorted(system.services.items()):
        out += ['/**', f' * The {s} service. Throw ServiceError when a call fails.', f' * @typedef {{Object}} {camel(s)}']
        for op, sig in ops.items():
            params = ', '.join(f'{n}: {js_type(t, namer)}' for n, t in sig.input.fields)
            out.append(f' * @property {{(args: {{{params}}}) => Promise<{namer.names[sig.output]}>}} {op}')
        out += [' */', '']
    out.append('''/**
 * Routes the flows' calls to your service objects:
 *   new Services({ payments: myPayments, inventory: myInventory })
 * Each method receives one object of named arguments.
 */
export class Services {
  constructor(impls) { this.impls = impls; }

  async call(service, op, args) {
    const impl = this.impls[service];
    if (!impl) throw new ServiceError(`no implementation for service ${service}`);
    return impl[op](args);
  }

  asFunction() { return (service, op, args) => this.call(service, op, args); }
}
''')
    return '\n'.join(out)


def _memory(system):
    keys = {e: rec.fields[0][0] for e, rec in system.entities.items()}
    out = ["// In-memory adapters: run and try the flows before real systems are connected.",
           "import { Services } from '../ports.js';", '',
           f'export const KEYS = {json.dumps(keys)};', '',
           '''export class MemoryStore {
  constructor() { this.records = {}; }

  async store(entity, op, data) {
    const rows = (this.records[entity] ||= []);
    const key = KEYS[entity];
    if (op === 'create') { rows.push({ ...data }); return; }
    this.records[entity] = rows.filter((r) => r[key] !== data[key]);
    if (op === 'update') this.records[entity].push({ ...data });
  }

  asFunction() { return (entity, op, data) => this.store(entity, op, data); }

  /** The records whose fields equal `where`, in stored order. */
  async query(entity, where) {
    return (this.records[entity] || [])
      .filter((r) => Object.entries(where).every(([k, v]) => r[k] === v)).map((r) => ({ ...r }));
  }

  queryFunction() { return (entity, where) => this.query(entity, where); }
}

/** An in-process message bus: publishing hands the message to every flow subscribed to
 *  the topic, right away. Replace with a real broker to go async. */
export class LocalTopics {
  constructor() { this.published = []; this.deliver = null; }

  async publish(topic, message) {
    this.published.push([topic, message]);
    if (this.deliver) await this.deliver(topic, message);
  }

  asFunction() { return (topic, message) => this.publish(topic, message); }
}

export class PrintNotifier {
  constructor(quiet = false) { this.sent = []; this.quiet = quiet; }

  async notify(channel, to, message) {
    this.sent.push([channel, to, message]);
    if (!this.quiet) console.log(`[${channel} -> ${to}] ${message}`);
  }

  asFunction() { return (channel, to, message) => this.notify(channel, to, message); }
}
''']
    values = fake_outputs(system)
    for s, ops in sorted(system.services.items()):
        out.append(f'/** Stands in for the {s} service: always succeeds, with the values of the passing test run. */\n'
                   f'export const fake{camel(s)} = {{')
        for op, sig in ops.items():
            out.append(f'  async {op}() {{ return {json.dumps(values[(s, op)])}; }},')
        out.append('};\n')
    fakes = ', '.join(f'{s}: fake{camel(s)}' for s in sorted(system.services))
    out.append(f'export const fakeServices = () => new Services({{ {fakes} }});')
    return '\n'.join(out) + '\n'


def _flow_module(flow):
    code = flow_code(flow, var(flow.name), export=True)
    form = 'structured' if 'state-machine form' not in code else 'state machine'
    used = [h for h in HELPERS if re.search(rf'(?<![\w.]){re.escape(h)}\b', code)]
    head = [f'// {flow.name}: {flow.intent or "generated flow"}',
            f'// Trigger: {trigger_line(flow)}   Mode: {flow.mode}   Form: {form}',
            '// Generated by Danta from IR2. Regenerate rather than edit by hand.']
    if used:
        head.append(f"import {{ {', '.join(used)} }} from '../runtime.js';")
    return '\n'.join(head) + '\n\n' + code + '\n'


def _flows_index(system):
    lines = ['// Every flow, by name, and what triggers it.']
    for f in system.flows:
        lines.append(f"import {{ {var(f.name)} }} from './{snake(f.name)}.js';")
    lines += ['', 'export const FLOWS = {'] + [f'  {json.dumps(f.name)}: {var(f.name)},' for f in system.flows] + ['};', '']
    meta = {f.name: {'source': f.trigger().source, 'mode': f.mode, **f.trigger().config} for f in system.flows}
    lines.append(f'export const TRIGGERS = {json.dumps(meta, indent=2)};')
    return '\n'.join(lines) + '\n'


APP = '''// Wiring: build an IO from adapters, and run a flow by name.
// The stand-ins are shared by every run, so records saved by one flow are there for the
// next, and messages published by one flow reach the flows listening.
// Adapters are chosen from config (environment variables): in memory by default, MongoDB /
// RabbitMQ / SMTP when configured.
import { config } from './config.js';
import { KEYS, LocalTopics, MemoryStore, PrintNotifier, fakeServices } from './adapters/memory.js';
import { MongoStore, RabbitTopics, SmtpNotifier } from './adapters/real.js';
import { FLOWS, TRIGGERS } from './flows/index.js';
import { execute } from './runtime.js';

export const STORE = config.store === 'mongo' ? new MongoStore(config.mongoUrl, config.mongoDb, KEYS) : new MemoryStore();
export const NOTIFIER = config.notify === 'smtp'
  ? new SmtpNotifier(config.smtpHost, config.smtpPort, config.smtpFrom, config.smtpUser, config.smtpPassword) : new PrintNotifier();
export const TOPICS = config.broker === 'rabbitmq' ? new RabbitTopics(config.rabbitmqUrl, config.service) : new LocalTopics();
const SUBSCRIBERS = {};
for (const [name, t] of Object.entries(TRIGGERS)) {
  if (t.source === 'topic') (SUBSCRIBERS[t.name] ||= []).push(name);
}

/** Real systems go here: makeIO({ services: new Services({...}).asFunction(), store, notify }). */
export function makeIO({ services, store, notify, query, publish } = {}) {
  return {
    services: services || fakeServices().asFunction(),
    store: store || STORE.asFunction(),
    query: query || STORE.queryFunction(),
    notify: notify || NOTIFIER.asFunction(),
    publish: publish || TOPICS.asFunction(),
    at: null,
  };
}

export function runFlow(name, request, io = makeIO()) {
  return execute(FLOWS[name], request, io);
}

/** Run every flow subscribed to `topic` with the message as its input. */
export async function deliver(topic, message) {
  const out = {};
  for (const name of SUBSCRIBERS[topic] || []) out[name] = await runFlow(name, { ...message });
  return out;
}

/** With a real broker, consume the subscribed topics in the background. */
export async function startConsumers() {
  if (Object.keys(SUBSCRIBERS).length && TOPICS.consume) {
    await TOPICS.consume(SUBSCRIBERS, (name, message) => runFlow(name, { ...message }));
  }
}

if (TOPICS instanceof LocalTopics) TOPICS.deliver = deliver;
'''

CONFIG = '''// Settings, from environment variables. The defaults run everything in memory.
const env = process.env;

export const config = {
  store: env.STORE || 'memory', // memory | mongo
  mongoUrl: env.MONGO_URL || 'mongodb://localhost:27017',
  mongoDb: env.MONGO_DB || '{pkg}',
  broker: env.BROKER || 'memory', // memory | rabbitmq
  rabbitmqUrl: env.RABBITMQ_URL || 'amqp://guest:guest@localhost:5672',
  notify: env.NOTIFY || 'print', // print | smtp
  smtpHost: env.SMTP_HOST || 'localhost',
  smtpPort: Number(env.SMTP_PORT || 1025),
  smtpFrom: env.SMTP_FROM || '{name}@example.com',
  smtpUser: env.SMTP_USER || '', // set both for a real relay (STARTTLS + login)
  smtpPassword: env.SMTP_PASSWORD || '',
  adminApi: env.ADMIN_API === '1',
  runScheduler: env.RUN_SCHEDULER !== '0', // 0 on replicas that must not run the scheduled flows
  service: '{name}',
};
'''

REAL = '''// Adapters for real infrastructure: MongoDB, RabbitMQ and SMTP (chosen in app.js from config).

/** Records in MongoDB, one collection per entity. Updates and deletes match the entity's key
 *  field; queries return records in the order they were stored. */
export class MongoStore {
  constructor(url, database, keys) {
    this.url = url; this.database = database; this.keys = keys; this.db = null;
  }

  async connect() {
    if (!this.db) {
      const { MongoClient } = await import('mongodb');
      const client = new MongoClient(this.url);
      await client.connect();
      this.db = client.db(this.database);
    }
    return this.db;
  }

  async store(entity, op, data) {
    const c = (await this.connect()).collection(entity);
    const key = this.keys[entity];
    if (op !== 'create') await c.deleteMany({ [key]: data[key] });
    if (op !== 'delete') await c.insertOne({ ...data });
  }

  async query(entity, where) {
    const rows = await (await this.connect()).collection(entity).find({ ...where }).sort({ _id: 1 }).toArray();
    return rows.map(({ _id, ...r }) => r);
  }

  asFunction() { return (entity, op, data) => this.store(entity, op, data); }
  queryFunction() { return (entity, where) => this.query(entity, where); }
}

/** Topics on a RabbitMQ topic exchange. Each subscribed flow has its own durable queue, so every
 *  flow gets every message and several app instances share the work. */
export class RabbitTopics {
  static EXCHANGE = 'flows';

  constructor(url, service) { this.url = url; this.service = service; this.channel = null; }

  async connect() {
    if (this.channel) return this.channel;
    const amqp = await import('amqplib');
    for (let attempt = 0; attempt < 30; attempt++) {
      try {
        const connection = await amqp.connect(this.url);
        const channel = await connection.createChannel();
        await channel.assertExchange(RabbitTopics.EXCHANGE, 'topic', { durable: true });
        this.channel = channel;
        return channel;
      } catch {
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
    throw new Error(`cannot reach RabbitMQ at ${this.url}`);
  }

  async publish(topic, message) {
    const channel = await this.connect();
    channel.publish(RabbitTopics.EXCHANGE, topic, Buffer.from(JSON.stringify(message)),
      { contentType: 'application/json', persistent: true });
  }

  /** Run handle(flowName, message) for every message on the subscribed topics. */
  async consume(subscribers, handle) {
    const channel = await this.connect();
    await channel.prefetch(1);
    for (const [topic, names] of Object.entries(subscribers)) {
      for (const name of names) {
        const queue = `${this.service}.${name}`;
        await channel.assertQueue(queue, { durable: true });
        await channel.bindQueue(queue, RabbitTopics.EXCHANGE, topic);
        await channel.consume(queue, async (msg) => {
          try {
            await handle(name, JSON.parse(msg.content.toString()));
          } catch (e) {
            console.error(`flow ${name} failed on a message`, e);
          }
          channel.ack(msg);
        });
      }
    }
    console.log(`consuming ${Object.keys(subscribers).join(', ')}`);
  }

  asFunction() { return (topic, message) => this.publish(topic, message); }
}

/** Sends email over SMTP (Mailpit catches it locally); other channels are logged. With a user
 *  and password (a real relay) it upgrades to TLS and logs in. */
export class SmtpNotifier {
  constructor(host, port, from, user = '', password = '') {
    this.host = host; this.port = port; this.from = from; this.user = user; this.password = password;
    this.transport = null;
  }

  async notify(channel, to, message) {
    if (channel !== 'email') { console.log(`[${channel} -> ${to}] ${message}`); return; }
    if (!this.transport) {
      const nodemailer = (await import('nodemailer')).default;
      this.transport = nodemailer.createTransport({
        host: this.host, port: this.port, secure: false,
        ...(this.user ? { requireTLS: true, auth: { user: this.user, pass: this.password } } : {}),
      });
    }
    await this.transport.sendMail({ from: this.from, to, subject: message.slice(0, 78), text: message });
  }

  asFunction() { return (channel, to, message) => this.notify(channel, to, message); }
}
'''

DOCKERFILE = '''FROM node:22-slim
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY src ./src
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["node", "src/main.js", "serve"]
'''

API = '''// HTTP API (Express): one endpoint per HTTP-triggered flow.
// Swagger UI is at /docs and the OpenAPI document at /openapi.json. The document is the one
// generated from the spec (openapi.json), so its request and response schemas are exact.
import express from 'express';
import swaggerUi from 'swagger-ui-express';
import { readFileSync } from 'node:fs';
import { config } from './config.js';
import { STORE, runFlow } from './app.js';
import { FLOWS, TRIGGERS } from './flows/index.js';

export const OPENAPI = JSON.parse(readFileSync(new URL('./openapi.json', import.meta.url), 'utf8'));
const DATA = {DATA};

export function createApp() {
  const app = express();
  app.use(express.json());
  app.get('/openapi.json', (req, res) => res.json(OPENAPI));
  app.use('/docs', swaggerUi.serve, swaggerUi.setup(OPENAPI));

  for (const [name, t] of Object.entries(TRIGGERS)) {
    if (t.source !== 'http') continue;
    app[t.method.toLowerCase()](t.path, async (req, res) => {
      const request = req.body && typeof req.body === 'object' ? req.body : {};
      if (t.mode === 'async') {
        runFlow(name, request).catch((e) => console.error(name, e));
        return res.status(202).json({ accepted: true });
      }
      try {
        const result = await runFlow(name, request);
        if (result.status === 'ok') return res.status(200).json(result.response || {});
        return res.status(422).json({ error: result.error, ...(result.response || {}) });
      } catch (e) {
        return res.status(400).json({ error: `missing or malformed field: ${e.message}` });
      }
    });
  }

  // The records the frontend's list screens read: GET /data/<entity>?field=value&...
  app.get('/data/:entity', async (req, res) => {
    const fields = DATA[req.params.entity];
    if (!fields) return res.status(404).json({ error: `no screen lists ${req.params.entity}` });
    const where = {};
    for (const [key, raw] of Object.entries(req.query)) {
      if (!fields[key]) return res.status(400).json({ error: `${req.params.entity} has no field ${key}` });
      if (fields[key] === 'int' && !/^-?\\d+$/.test(raw)) return res.status(400).json({ error: `${key} must be a whole number` });
      where[key] = fields[key] === 'int' ? Number(raw) : fields[key] === 'bool' ? raw === 'true' : raw;
    }
    res.json(await STORE.query(req.params.entity, where));
  });

  if (config.adminApi) {
    // Local testing only (ADMIN_API=1): run any flow, and read or seed records.
    app.post('/admin/flows/:name', async (req, res) => {
      if (!FLOWS[req.params.name]) return res.status(404).json({ error: `unknown flow ${req.params.name}` });
      res.json(await runFlow(req.params.name, req.body || {}));
    });
    app.get('/admin/store/:entity', async (req, res) => res.json(await STORE.query(req.params.entity, {})));
    app.post('/admin/store/:entity', async (req, res) => {
      await STORE.store(req.params.entity, 'create', req.body);
      res.json({ created: true });
    });
  }

  // a body that isn't JSON
  app.use((err, req, res, next) => {
    if (err.type === 'entity.parse.failed') return res.status(400).json({ error: 'the body must be JSON' });
    return next(err);
  });
  return app;
}

export function serve(port = 8000, host = '127.0.0.1') {
  return createApp().listen(port, host, () => console.log(`listening on http://${host}:${port}/  (docs at /docs)`));
}
'''

EVENTS = '''// Event entry points: publish(eventName, payload) runs the flow listening for it.
import { runFlow } from '../app.js';
import { TRIGGERS } from '../flows/index.js';

export const EVENTS = Object.fromEntries(Object.entries(TRIGGERS)
  .filter(([, t]) => t.source === 'event').map(([name, t]) => [t.name, name]));

export function publish(event, payload, io) {
  const name = EVENTS[event];
  if (!name) throw new Error(`no flow listens for event ${event}`);
  return runFlow(name, payload, io);
}
'''

SCHEDULE = '''// Scheduled flows: runDue() runs every flow whose cron matches the current minute.
import { runFlow } from '../app.js';
import { TRIGGERS } from '../flows/index.js';
import { cronMatches } from '../runtime.js';

export const SCHEDULES = Object.entries(TRIGGERS)
  .filter(([, t]) => t.source === 'schedule').map(([name, t]) => [t.cron, name]);

const today = (when) => when.toISOString().slice(0, 10);

/** The payload a scheduled run receives. Edit to suit. */
export const PAYLOADS = {PAYLOAD_BUILDERS};

export async function runDue(when = new Date(), io) {
  const out = {};
  for (const [cron, name] of SCHEDULES) {
    if (cronMatches(cron, when)) out[name] = await runFlow(name, PAYLOADS[name](when), io);
  }
  return out;
}

export function loop(ioFactory) {
  let last = null;
  return setInterval(async () => {
    const now = new Date(); now.setSeconds(0, 0);
    if (last && now.getTime() === last) return;
    last = now.getTime();
    const results = await runDue(now, ioFactory ? ioFactory() : undefined);
    for (const [name, r] of Object.entries(results)) console.log(`${now.toISOString()} ${name}: ${r.status}`);
  }, 5000);
}
'''

MAIN = '''// node src/main.js <command>
//   serve [port]          the HTTP API (Swagger UI at /docs), plus the scheduler
//   run FLOW 'JSON'       run one flow with a JSON payload
//   event NAME 'JSON'     publish an event
//   tick                  run the scheduled flows due this minute
import { TOPICS, runFlow, startConsumers } from './app.js';
import { config } from './config.js';
import { FLOWS } from './flows/index.js';
import { publish } from './triggers/events.js';
import { serve } from './api.js';
import { SCHEDULES, loop, runDue } from './triggers/schedule.js';

const [command, name, payload = '{}'] = process.argv.slice(2);
if (command === 'serve') {
  if (SCHEDULES.length && config.runScheduler) loop();
  await startConsumers();
  serve(Number(name) || Number(process.env.PORT) || 8000, process.env.HOST || '127.0.0.1');
} else if (command === 'run') {
  if (!FLOWS[name]) { console.error(`unknown flow ${name} (flows: ${Object.keys(FLOWS).join(', ')})`); process.exit(1); }
  console.log(JSON.stringify(await runFlow(name, JSON.parse(payload)), null, 2));
} else if (command === 'event') {
  console.log(JSON.stringify(await publish(name, JSON.parse(payload)), null, 2));
} else if (command === 'publish') {
  await TOPICS.publish(name, JSON.parse(payload));
  console.log(`published to ${name}`);
} else if (command === 'tick') {
  console.log(JSON.stringify(await runDue(), null, 2));
} else {
  console.error('usage: node src/main.js serve [port] | run FLOW JSON | event NAME JSON | tick');
  process.exit(1);
}
'''

TEST = '''// {flow}: every generated scenario, replayed. Generated from the reference simulator.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { {fn} } from '../src/flows/{module}.js';
import { ServiceError, execute } from '../src/runtime.js';

const SCENARIOS = {scenarios};
const KEYS = {keys};

async function replay(scenario) {
  const mocks = scenario.mocks || {}, effects = [], attempts = {};
  const rows = structuredClone(scenario.store || {});
  const io = {
    at: null,
    services: async (service, op, args, step) => {
      const n = attempts[step] = (attempts[step] || 0) + 1;
      const outcomes = Array.isArray(mocks[step]) ? mocks[step] : [mocks[step]];
      const outcome = outcomes[Math.min(n, outcomes.length) - 1];
      effects.push(`call ${service}.${op} #${n}`);
      if ('ok' in outcome) return structuredClone(outcome.ok);
      throw new ServiceError(outcome.error);
    },
    store: async (entity, op, data) => {
      effects.push(`persist ${entity}.${op}`);
      const table = (rows[entity] ||= []);
      if (op === 'create') { table.push({ ...data }); return; }
      rows[entity] = table.filter((r) => r[KEYS[entity]] !== data[KEYS[entity]]);
      if (op === 'update') rows[entity].push({ ...data });
    },
    query: async (entity, where) => (rows[entity] || [])
      .filter((r) => Object.entries(where).every(([k, v]) => r[k] === v)).map((r) => ({ ...r })),
    publish: async (topic, message) => { effects.push(`publish ${topic} ${JSON.stringify(message)}`); },
    notify: async (channel, to, message) => { effects.push(`notify ${channel} ${to}: ${message}`); },
  };
  const result = await execute({fn}, structuredClone(scenario.input), io);
  return { result, effects };
}

for (const [name, scenario] of Object.entries(SCENARIOS)) {
  test(name, async () => {
    const { result, effects } = await replay(scenario);
    assert.equal(result.status, scenario.expect.status);
    assert.deepEqual(result.response, scenario.expect.response ?? null);
    assert.deepEqual(effects, scenario.expect.effects);
  });
}
'''


API_TEST = '''// The HTTP API: the OpenAPI document and Swagger UI are served, and every HTTP-triggered
// flow answers (with the in-memory stand-ins in place).
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/api.js';

const CALLS = {calls};
let server, base;

before(async () => {
  server = createApp().listen(0);
  await new Promise((resolve) => server.once('listening', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => server.close());

test('openapi document', async () => {
  const r = await fetch(`${base}/openapi.json`);
  assert.equal(r.status, 200);
  assert.equal((await r.json()).info.title, {title});
});

test('swagger ui', async () => {
  assert.equal((await fetch(`${base}/docs/`)).status, 200);
});

for (const call of CALLS) {
  test(`${call.method} ${call.path}`, async () => {
    const r = await fetch(`${base}${call.path}`, {
      method: call.method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(call.body),
    });
    assert.ok(call.expect.includes(r.status), `status ${r.status}`);
  });
}
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
        fields = ', '.join(f'{n}: {"today(when)" if ft == STR else _default(ft)}' for n, ft in t.payload.fields)
        items.append(f'\n  {json.dumps(f.name)}: (when) => ({{ {fields} }}),')
    return '{' + ''.join(items) + ('\n}' if items else '}')


def _readme(system):
    lines = [f'# {system.name}', '']
    if system.description:
        lines += [system.description, '']
    lines += ['Generated by Danta from a Danta Spec. Every flow was verified against the',
              'reference simulator; `test/` replays those scenarios, so keep them passing when you edit.',
              'No dependencies: Node.js 18 or newer.', '', '## Flows', '']
    for f in system.flows:
        lines += [f'### {f.name}', '', f'`{trigger_line(f)}`, {f.mode}.', '']
        if f.intent:
            lines += [f.intent, '']
        lines += outline(f) + ['']
    first = system.flows[0].name
    lines += infra.readme_section(system, 8000, '`npm start`.')
    lines += frontend.readme_section(system, 8000)
    lines += ['## Run', '', '```bash', 'npm install', 'npm test', 'npm start                      # http://127.0.0.1:8000/docs',
              f"node src/main.js run {first} '{{...}}'",
              '```', '', '## Connect real systems', '',
              'Implement the service interfaces documented in `src/ports.js` and pass them to `makeIO`:', '',
              '```js', "import { makeIO, runFlow } from './src/app.js';", "import { Services } from './src/ports.js';", '',
              'const io = makeIO({ services: new Services({ '
              + ', '.join(f'{s}: my{camel(s)}' for s in sorted(system.services)) + ' }).asFunction(),',
              '                    store: myStore, notify: myNotifier });', f"await runFlow('{first}', payload, io);",
              '```', '', 'Parallel steps run one after another, in the order written. Integers are signed 32-bit',
              '(money in cents) and wrap on overflow, exactly as in the spec.', '']
    return '\n'.join(lines)


def generate(system):
    root = system.name
    namer = collect_types(system)
    files = {
        f'{root}/package.json': json.dumps({
            'name': system.name, 'version': '0.1.0', 'private': True, 'type': 'module',
            'description': (system.description or 'Generated by Danta')[:200],
            'engines': {'node': '>=18'},
            'scripts': {'start': 'node src/main.js serve', 'test': 'node --test test/*.test.js'},
            'dependencies': {'express': '^4.21.0', 'swagger-ui-express': '^5.0.1', 'mongodb': '^6.8.0',
                             'amqplib': '^0.10.4', 'nodemailer': '^6.9.14'},
        }, indent=2) + '\n',
        f'{root}/README.md': _readme(system),
        f'{root}/src/runtime.js': '// Shared runtime for the generated flows: results, service calls, 32-bit arithmetic.\n'
                                  + RUNTIME.strip() + '\n' + EXECUTE,
        f'{root}/src/models.js': _models(namer),
        f'{root}/src/ports.js': _ports(system, namer),
        f'{root}/src/app.js': APP,
        f'{root}/src/main.js': MAIN,
        f'{root}/src/flows/index.js': _flows_index(system),
        f'{root}/src/api.js': API.replace('{DATA}', json.dumps(data_entities(system))),
        f'{root}/src/config.js': CONFIG.replace('{pkg}', snake(system.name)).replace('{name}', system.name),
        f'{root}/src/adapters/real.js': REAL,
        f'{root}/Dockerfile': DOCKERFILE,
        f'{root}/.dockerignore': 'node_modules\ntest\n.git\n',
        f'{root}/docker-compose.yml': infra.compose(system, 8000, 'node'),
        f'{root}/.env.example': infra.env_example(system, 8000),
        f'{root}/src/openapi.json': json.dumps(openapi(system), indent=2) + '\n',
        f'{root}/docs/asyncapi.json': json.dumps(asyncapi(system), indent=2) + '\n',
        f'{root}/test/api.test.js': (API_TEST.replace('{calls}', json.dumps(_api_calls(system), indent=1))
                                     .replace('{title}', json.dumps(system.name))),
        f'{root}/.gitignore': 'node_modules/\n',
        f'{root}/src/triggers/events.js': EVENTS,
        f'{root}/src/triggers/schedule.js': SCHEDULE.replace('{PAYLOAD_BUILDERS}', _payload_builders(system)),
        f'{root}/src/adapters/memory.js': _memory(system),
    }
    for f in system.flows:
        mod = snake(f.name)
        files[f'{root}/src/flows/{mod}.js'] = _flow_module(f)
        files[f'{root}/test/{mod}.test.js'] = (TEST.replace('{flow}', f.name).replace('{fn}', var(f.name))
                                               .replace('{module}', mod)
                                               .replace('{keys}', json.dumps({e: rec.fields[0][0] for e, rec in system.entities.items()}))
                                               .replace('{scenarios}', json.dumps(system.scenarios.get(f.name, {}), indent=1)))
    files.update(frontend.generate_web(system, 8000))
    files.update({f'{root}/{k}': v for k, v in deploy.manifests(system, 8000, 'IMAGE').items()})
    return files
