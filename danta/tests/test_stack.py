"""The generated docker-compose stacks, end to end: real MongoDB, RabbitMQ and Mailpit.

Slow (it builds images), so it only runs when asked:

    FLOW_STACK_TESTS=1 python -m unittest danta.tests.test_stack

For each language, the invoice-chaser batch runs over seeded invoices; its
reminders travel through RabbitMQ to the worker flow, which emails through
Mailpit and marks the invoices reminded in MongoDB. Then the help desk's web
app (nginx on :3000) opens and closes a ticket through /api, as its screens do.
"""

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request

from danta.codegen.project import generate, write
from danta.tests.test_project import batch, help_desk, system_from

PORTS = {'python': 8000, 'javascript': 8000, 'java': 8080}
INVOICES = [
    {'invoice_id': 'I-1', 'customer_email': 'ana@shop.test', 'amount': 5000, 'days_late': 45, 'status': 'open'},
    {'invoice_id': 'I-2', 'customer_email': 'bo@shop.test', 'amount': 800, 'days_late': 5, 'status': 'paid'},
    {'invoice_id': 'I-3', 'customer_email': 'cy@shop.test', 'amount': 1200, 'days_late': 12, 'status': 'open'},
]


def docker_ready():
    if not shutil.which('docker'):
        return False
    return subprocess.run(['docker', 'info'], capture_output=True).returncode == 0


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read() or b'null')


@unittest.skipUnless(os.environ.get('FLOW_STACK_TESTS') == '1' and docker_ready(),
                     'set FLOW_STACK_TESTS=1 with a running Docker')
class Stacks(unittest.TestCase):
    def test_batch_reminders_flow_through_the_real_stack(self):
        system = system_from(batch())
        for lang, port in PORTS.items():
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as tmp:
                write(generate(system, lang), tmp)
                self.check_stack(os.path.join(tmp, 'invoice-chaser'), port, f'flowstack-{lang}')

    def test_the_web_app_drives_the_flows_through_nginx(self):
        system = system_from(help_desk())
        for lang in PORTS:
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as tmp:
                write(generate(system, lang), tmp)
                with self.stack(os.path.join(tmp, 'help-desk'), f'webstack-{lang}'):
                    web = 'http://localhost:3000'
                    with urllib.request.urlopen(f'{web}/open-tickets', timeout=10) as r:
                        self.assertIn('<div id="root">', r.read().decode())      # the app, for any path
                    ticket = {'ticket_id': 'T-1', 'customer_email': 'ana@shop.test',
                              'subject': 'Checkout crashes', 'priority': 'urgent'}
                    self.assertEqual(http('POST', f'{web}/api/tickets', ticket), (200, {'ticket_id': 'T-1', 'status': 'open'}))
                    self.assertEqual(len(http('GET', f'{web}/api/data/ticket?status=open')[1]), 1)
                    http('POST', f'{web}/api/tickets/close', ticket)
                    self.assertEqual(http('GET', f'{web}/api/data/ticket?status=open')[1], [])
                    self.assertEqual(http('GET', f'{web}/api/data/ticket?status=closed')[1][0]['ticket_id'], 'T-1')

    @contextlib.contextmanager
    def stack(self, root, project):
        def compose(*args, timeout=600):
            return subprocess.run(['docker', 'compose', '-p', project, *args], cwd=root,
                                  capture_output=True, text=True, timeout=timeout)

        up = compose('up', '-d', '--build', '--wait', timeout=1800)
        try:
            self.assertEqual(up.returncode, 0, up.stderr[-3000:] + compose('logs').stdout[-3000:])
            yield
        finally:
            compose('down', '-v')

    def check_stack(self, root, port, project):
        with self.stack(root, project):
            base = f'http://localhost:{port}'
            self.assertEqual(http('GET', f'{base}/openapi.json')[0], 200)
            for invoice in INVOICES:
                http('POST', f'{base}/admin/store/invoice', invoice)
            http('POST', f'{base}/admin/flows/find_overdue', {'run_date': '2026-09-28'})
            deadline = time.time() + 30
            while True:
                rows = http('GET', f'{base}/admin/store/invoice')[1]
                statuses = {r['invoice_id']: r['status'] for r in rows}
                if list(statuses.values()).count('reminded') == 2 or time.time() > deadline:
                    break
                time.sleep(1)
            self.assertEqual(statuses, {'I-1': 'reminded', 'I-2': 'paid', 'I-3': 'reminded'})
            mail = http('GET', 'http://localhost:8025/api/v1/messages')[1]
            self.assertEqual(sorted(m['To'][0]['Address'] for m in mail['messages']), ['ana@shop.test', 'cy@shop.test'])


if __name__ == '__main__':
    unittest.main()
