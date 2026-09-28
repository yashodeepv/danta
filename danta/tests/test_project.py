"""Generated projects: complete layout, and their own test suites pass."""

import json
import os
import random
import shutil
import subprocess
import tempfile
import unittest

from danta.app.pipeline import FlowHints
from danta.app.prompt import example_spec
from danta.codegen.format import format_project
from danta.codegen.project import System, generate, verify_project, zip_bytes
from danta.codegen.verify import node_available
from danta.gen.coverage import synthesize
from danta.spec import compile_spec


def maven():
    return shutil.which('mvn') is not None


def system_from(text):
    res = compile_spec(text)
    assert res.ok, res.errors
    rng = random.Random(0)
    return System(res.system, res.description, res.flows,
                  {f.name: synthesize(rng, f, FlowHints(f))[0] for f in res.flows}, res.screens)


def checkout():
    with open('danta/spec/examples/order_checkout.spec.md') as f:
        return f.read().replace('the sum of the item amounts', '`sum(items.amount)`')


class Projects(unittest.TestCase):
    def test_python_layout(self):
        files = generate(system_from(checkout()), 'python')
        for path in ['pyproject.toml', 'README.md', 'src/shop_orders/runtime.py', 'src/shop_orders/models.py',
                     'src/shop_orders/ports.py', 'src/shop_orders/flows/order_checkout.py',
                     'src/shop_orders/api.py', 'src/shop_orders/openapi.json', 'docs/asyncapi.json',
                     'tests/test_api.py', 'src/shop_orders/adapters/memory.py',
                     'tests/test_order_checkout.py']:
            self.assertIn(f'shop-orders/{path}', files)
        flow = files['shop-orders/src/shop_orders/flows/order_checkout.py']
        self.assertIn('def order_checkout(request, io):', flow)
        self.assertIn('Form: structured', flow)
        self.assertIn('class Payments(Protocol):', files['shop-orders/src/shop_orders/ports.py'])

    def test_javascript_layout(self):
        files = generate(system_from(checkout()), 'javascript')
        for path in ['package.json', 'README.md', 'src/runtime.js', 'src/flows/order_checkout.js',
                     'src/api.js', 'src/openapi.json', 'docs/asyncapi.json', 'test/api.test.js',
                     'test/order_checkout.test.js']:
            self.assertIn(f'shop-orders/{path}', files)
        self.assertIn('export async function order_checkout(request, io)',
                      files['shop-orders/src/flows/order_checkout.js'])

    def test_java_is_a_spring_boot_project(self):
        files = generate(system_from(checkout()), 'java')
        base = 'shop-orders/src/main/java/shop_orders'
        for path in ['shop-orders/pom.xml', 'shop-orders/README.md', f'{base}/Application.java',
                     f'{base}/runtime/R.java', f'{base}/Models.java', f'{base}/ports/Payments.java',
                     f'{base}/ports/ServiceRouter.java', f'{base}/adapters/FakePayments.java',
                     f'{base}/flows/OrderCheckoutFlow.java', f'{base}/web/FlowController.java',
                     'shop-orders/src/test/java/shop_orders/flows/OrderCheckoutFlowTest.java',
                     'shop-orders/src/test/resources/scenarios/order_checkout.json']:
            self.assertIn(path, files)
        self.assertIn('spring-boot-starter-web', files['shop-orders/pom.xml'])
        self.assertIn('@SpringBootApplication', files[f'{base}/Application.java'])
        self.assertIn('@PostMapping("/orders")', files[f'{base}/web/FlowController.java'])
        self.assertIn('@Service', files[f'{base}/flows/OrderCheckoutFlow.java'])
        self.assertIn('springdoc-openapi-starter-webmvc-ui', files['shop-orders/pom.xml'])
        self.assertIn('shop-orders/src/main/resources/static/openapi.json', files)
        self.assertIn('Models.PaymentsChargeResult charge(String order_id, int amount)',
                      files[f'{base}/ports/Payments.java'])

    def test_spring_cron_gets_a_seconds_field(self):
        from danta.codegen.project.java_project import spring_cron
        self.assertEqual(spring_cron('0 6 * * *'), '0 0 6 * * *')

    def test_generated_test_suites_pass(self):
        with open('danta/spec/examples/invoice_batch.spec.md') as fh:
            batch = fh.read()
        for text in (checkout(), example_spec(), batch, help_desk()):
            system = system_from(text)
            for lang in ('python', 'javascript', 'java'):
                if (lang == 'javascript' and not node_available()) or (lang == 'java' and not maven()):
                    continue
                with self.subTest(system=system.name, lang=lang):
                    # formatted first: the files a user downloads are the files tested
                    files, fmt = format_project(generate(system, lang), lang)
                    rep = verify_project(files, lang)
                    self.assertEqual(rep['status'], 'verified', rep['detail'])
                    self.assertGreater(rep['total'], 2)

    def test_a_system_with_several_flows_is_one_project(self):
        extra = ('\n## Flow: cancel_leave\nTrigger: event leave_cancelled with employee_id str, '
                 'manager_email str, days int\nMode: async\nSteps:\n'
                 '1. [Remove the request] Delete leave_request where employee_id.\n'
                 '2. [Tell the manager] Email manager_email: "{employee_id} cancelled {days} days".\n')
        system = system_from(example_spec() + extra)
        for lang in ('python', 'javascript'):
            if lang == 'javascript' and not node_available():
                continue
            files = generate(system, lang)
            with self.subTest(lang=lang):
                self.assertEqual(len([p for p in files if '/flows/' in p and ('cancel' in p or 'request_leave' in p)]), 2)
                rep = verify_project(files, lang)
                self.assertEqual(rep['status'], 'verified', rep['detail'])

    def test_generated_tests_catch_a_bug(self):
        files = generate(system_from(checkout()), 'python')
        path = 'shop-orders/src/shop_orders/flows/order_checkout.py'
        files[path] = files[path].replace("pricing['subtotal'] - pricing['discount']",
                                          "pricing['subtotal'] + pricing['discount']")
        self.assertEqual(verify_project(files, 'python')['status'], 'failed')

    def test_fakes_walk_the_happy_path(self):
        # a fake answering is_valid = false (a blank placeholder) would fail every request to the running app
        from danta.codegen.project.common import fake_outputs
        spec = ('Spec: danta/0.1\n\n# System: leads\n\n## Services\n'
                '- enrichment.get_score(email str) -> (score int, is_valid bool)\n\n'
                '## Flow: ingest\nTrigger: POST /leads with email str\nMode: sync\nSteps:\n'
                '1. Call enrichment.get_score with email.\n'
                '2. Validate: `get_score.is_valid`. Otherwise stop with error "invalid email".\n'
                '3. Validate: `get_score.score >= 20`. Otherwise stop with error "junk".\n'
                '4. Respond with email.\n')
        values = fake_outputs(system_from(spec))[('enrichment', 'get_score')]
        self.assertIs(values['is_valid'], True)
        self.assertGreaterEqual(values['score'], 20)

    def test_errors_report_the_spec_message(self):
        from danta.sim import run
        system = system_from(checkout())
        res = run(system.flows[0], {'order_id': 'o1', 'customer_email': 'a@b.c', 'tier': 'gold', 'items': []})
        self.assertEqual(res.error, 'order has no items')

    def test_zip(self):
        import io
        import zipfile
        files = generate(system_from(checkout()), 'python')
        with zipfile.ZipFile(io.BytesIO(zip_bytes(files))) as z:
            self.assertEqual(sorted(z.namelist()), sorted(files))


def help_desk():
    with open('danta/spec/examples/help_desk.spec.md') as f:
        return f.read()


def batch():
    with open('danta/spec/examples/invoice_batch.spec.md') as f:
        return f.read()


class DockerAndDeploy(unittest.TestCase):
    """Every project runs locally with docker compose and ships Kubernetes manifests."""

    def test_every_language_ships_docker_and_deploy_files(self):
        system = system_from(batch())
        for lang in ('python', 'javascript', 'java'):
            files = generate(system, lang)
            with self.subTest(lang=lang):
                for path in ['Dockerfile', '.dockerignore', 'docker-compose.yml', '.env.example', 'deploy/DEPLOY.md',
                             'deploy/k8s/configmap.yaml', 'deploy/k8s/secret.example.yaml', 'deploy/k8s/web.yaml',
                             'deploy/k8s/scheduler.yaml', 'deploy/k8s/hpa.yaml', 'deploy/k8s/ingress.yaml']:
                    self.assertIn(f'invoice-chaser/{path}', files)
                compose = files['invoice-chaser/docker-compose.yml']
                for image in ('mongo:', 'rabbitmq:', 'mailpit'):
                    self.assertIn(image, compose)
                self.assertIn('deploy/DEPLOY.md', files['invoice-chaser/README.md'])

    def test_the_scheduler_runs_on_exactly_one_replica(self):
        files = generate(system_from(batch()), 'python')
        web, scheduler = files['invoice-chaser/deploy/k8s/web.yaml'], files['invoice-chaser/deploy/k8s/scheduler.yaml']
        self.assertIn('value: "0"', web)
        self.assertIn('replicas: 1', scheduler)
        self.assertIn('value: "1"', scheduler)
        # a system without schedules has no scheduler Deployment
        self.assertNotIn('shop-orders/deploy/k8s/scheduler.yaml', generate(system_from(checkout()), 'python'))

    def test_only_the_infrastructure_a_system_uses_is_configured(self):
        # the leave desk stores records and sends email, but publishes to no topic
        files = generate(system_from(example_spec()), 'python')
        compose = files['leave-desk/docker-compose.yml']
        self.assertIn('mongo:', compose)
        self.assertNotIn('rabbitmq:', compose)
        self.assertNotIn('RABBITMQ_URL', files['leave-desk/deploy/k8s/secret.example.yaml'])

    def test_screens_add_a_react_app_to_every_backend(self):
        system = system_from(help_desk())
        for lang in ('python', 'javascript', 'java'):
            files = generate(system, lang)
            with self.subTest(lang=lang):
                for path in ['web/package.json', 'web/src/App.jsx', 'web/src/ui.jsx', 'web/src/api.js',
                             'web/src/screens/NewTicket.jsx', 'web/src/screens/NewTicket.test.jsx',
                             'web/src/screens/OpenTickets.jsx', 'web/Dockerfile', 'deploy/k8s/frontend.yaml']:
                    self.assertIn(f'help-desk/{path}', files)
                self.assertIn('build: ./web', files['help-desk/docker-compose.yml'])
                self.assertIn('send("POST", "/tickets/close"', files['help-desk/web/src/screens/OpenTickets.jsx'])
                self.assertIn('/data/ticket', json.loads(next(v for k, v in files.items() if k.endswith('openapi.json')))['paths'])
        # the React app is the same whichever the backend (only the files naming its port differ)
        def web(files):
            return {k: v for k, v in files.items() if k.startswith('help-desk/web/') and not k.endswith(('Dockerfile', 'vite.config.js'))}
        self.assertEqual(web(generate(system, 'python')), web(generate(system, 'java')))
        # without screens, no web app
        self.assertFalse([p for p in generate(system_from(batch()), 'python') if p.startswith('invoice-chaser/web/')])

    @unittest.skipUnless(shutil.which('kubeconform'), 'kubeconform not installed')
    def test_manifests_are_valid_kubernetes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for text in (checkout(), example_spec(), batch()):
                for path, body in generate(system_from(text), 'python').items():
                    if path.endswith('.yaml') and '/deploy/k8s/' in path:
                        full = os.path.join(tmp, path)
                        os.makedirs(os.path.dirname(full), exist_ok=True)
                        with open(full, 'w') as f:
                            f.write(body)
            # -ignore-missing-schemas: GKE's ManagedCertificate is a CRD with no published schema
            r = subprocess.run(['kubeconform', '-strict', '-summary', '-ignore-missing-schemas', tmp],
                               capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
