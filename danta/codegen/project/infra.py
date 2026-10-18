"""infra.py - What a system needs to run for real, and the files that stand it up.

Shared by the three project generators:

    needs(system)          which infrastructure the flows use: mongo, rabbitmq, mailpit
    compose(system, app)   docker-compose.yml: the app plus exactly that infrastructure
    env_example(...)       .env.example documenting every setting

Settings, the same names in every language:

    STORE=memory|mongo          MONGO_URL, MONGO_DB
    BROKER=memory|rabbitmq      RABBITMQ_URL
    NOTIFY=print|smtp           SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_USER, SMTP_PASSWORD
    ADMIN_API=0|1               /admin endpoints: run any flow, read and seed records
    HOST, PORT                  where the HTTP API listens
"""

from danta.ir2 import graph as g
from danta.codegen.project.common import snake


def needs(system):
    steps = [s for f in system.flows for s in f.steps]
    return {
        'mongo': any(isinstance(s, (g.Persist, g.Query)) for s in steps),
        'rabbitmq': any(isinstance(s, g.Publish) for s in steps)
                    or any(f.trigger().source == 'topic' for f in system.flows),
        'mailpit': any(isinstance(s, g.Notify) and s.channel == 'email' for s in steps),
    }


def app_env(system):
    n = needs(system)
    env = {'ADMIN_API': '1', 'HOST': '0.0.0.0'}
    if n['mongo']:
        env.update(STORE='mongo', MONGO_URL='mongodb://mongo:27017', MONGO_DB=snake(system.name))
    if n['rabbitmq']:
        env.update(BROKER='rabbitmq', RABBITMQ_URL='amqp://guest:guest@rabbitmq:5672')
    if n['mailpit']:
        env.update(NOTIFY='smtp', SMTP_HOST='mailpit', SMTP_PORT='1025', SMTP_FROM=f'{system.name}@example.com')
    return env


HEALTH = {
    'python': '["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen(\'http://localhost:{port}/openapi.json\')"]',
    'node': '["CMD", "node", "-e", "fetch(\'http://localhost:{port}/openapi.json\').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]',
    'java': '["CMD-SHELL", "bash -c \'</dev/tcp/127.0.0.1/{port}\' || exit 1"]',
}


def compose(system, port, runtime, extra_env=None, extra_services=''):
    """docker-compose.yml for the app (built from ./Dockerfile) and its infrastructure."""
    n = needs(system)
    env = {**app_env(system), **(extra_env or {})}
    deps = []
    if n['mongo']:
        deps.append('      mongo:\n        condition: service_healthy')
    if n['rabbitmq']:
        deps.append('      rabbitmq:\n        condition: service_healthy')
    if n['mailpit']:
        deps.append('      mailpit:\n        condition: service_started')
    lines = [f'# {system.name}: the app and the infrastructure its flows use.',
             '#   docker compose up --build', f'#   API and Swagger UI: http://localhost:{port}/docs']
    if system.screens:
        lines.append('#   Web app: http://localhost:3000')
    if n['mailpit']:
        lines.append('#   Emails sent by the flows: http://localhost:8025')
    if n['rabbitmq']:
        lines.append('#   RabbitMQ console: http://localhost:15672 (guest / guest)')
    lines += ['services:', '  app:', '    build: .', '    restart: unless-stopped', '    ports:', f'      - "{port}:{port}"',
              '    environment:']
    lines += [f'      {k}: "{v}"' for k, v in env.items()]
    if deps:
        lines += ['    depends_on:'] + deps
    lines += ['    healthcheck:', f'      test: {HEALTH[runtime].replace("{port}", str(port))}',
              '      interval: 5s', '      retries: 60']
    if n['mongo']:
        lines += ['  mongo:', '    image: mongo:7', '    ports:', '      - "27017:27017"', '    volumes:',
                  '      - mongo-data:/data/db', '    healthcheck:',
                  '      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand(\'ping\')"]',
                  '      interval: 5s', '      retries: 30']
    if n['rabbitmq']:
        lines += ['  rabbitmq:', '    image: rabbitmq:3.13-management', '    ports:', '      - "5672:5672"',
                  '      - "15672:15672"', '    healthcheck:',
                  '      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]', '      interval: 5s', '      retries: 40']
    if n['mailpit']:
        lines += ['  mailpit:', '    image: axllent/mailpit:latest', '    ports:', '      - "8025:8025"',
                  '      - "1025:1025"']
    if system.screens:
        lines += ['  web:', '    build: ./web', '    restart: unless-stopped', '    ports:', '      - "3000:80"',
                  '    environment:', f'      API_URL: "http://app:{port}"', '    depends_on:', '      app:',
                  '        condition: service_healthy', '    healthcheck:',
                  '      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1/"]',
                  '      interval: 5s', '      retries: 30']
    if extra_services:
        lines.append(extra_services.rstrip())
    if n['mongo']:
        lines += ['volumes:', '  mongo-data: {}']
    return '\n'.join(lines) + '\n'


def env_example(system, port):
    n = needs(system)
    return '\n'.join([
        f'# {system.name} settings. The defaults run everything in memory; docker-compose.yml sets the rest.',
        'STORE=memory            # memory | mongo',
        'MONGO_URL=mongodb://localhost:27017',
        f'MONGO_DB={snake(system.name)}',
        'BROKER=memory           # memory | rabbitmq',
        'RABBITMQ_URL=amqp://guest:guest@localhost:5672',
        'NOTIFY=print            # print | smtp (email only; other channels are logged)',
        'SMTP_HOST=localhost',
        'SMTP_PORT=1025',
        f'SMTP_FROM={system.name}@example.com',
        'SMTP_USER=               # a real relay: set both, and the app uses STARTTLS + login',
        'SMTP_PASSWORD=',
        'ADMIN_API=0             # 1 enables /admin: run any flow, read and seed records',
        'HOST=127.0.0.1',
        f'PORT={port}',
        '',
        f'# This system uses: ' + (', '.join(k for k, v in n.items() if v) or 'no infrastructure'),
    ]) + '\n'


def readme_section(system, port, run_line):
    n = needs(system)
    lines = ['## Run the whole stack locally', '', 'With Docker (or Colima) running:', '', '```bash',
             'docker compose up --build', '```', '',
             f'- API and Swagger UI: http://localhost:{port}/docs']
    if system.screens:
        lines.append('- Admin panel: http://localhost:3000 (or 3001 if a design spec is also built)')
    if n['mailpit']:
        lines.append('- Emails the flows send: http://localhost:8025 (Mailpit)')
    if n['rabbitmq']:
        lines.append('- Topics: RabbitMQ console at http://localhost:15672 (guest / guest)')
    if n['mongo']:
        lines.append('- Data: MongoDB at `mongodb://localhost:27017`')
    lines += ['', 'The stack enables the admin API (`ADMIN_API=1`), handy for trying flows that aren\'t',
              'triggered over HTTP:', '', '```bash',
              f'curl -X POST localhost:{port}/admin/flows/<flow> -H "Content-Type: application/json" -d \'{{...}}\'',
              f'curl -X POST localhost:{port}/admin/store/<entity> -H "Content-Type: application/json" -d \'{{...}}\'',
              f'curl localhost:{port}/admin/store/<entity>', '```', '',
              'Without Docker, everything runs in memory: ' + run_line, '',
              '## Deploy', '',
              'Kubernetes manifests are in `deploy/k8s/`; [deploy/DEPLOY.md](deploy/DEPLOY.md) walks through',
              'Google Cloud (GKE) step by step, with notes for AWS (EKS), Azure (AKS) and Cloud Run.', '']
    return lines
