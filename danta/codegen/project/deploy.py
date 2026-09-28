"""deploy.py - Kubernetes manifests and a deployment guide, for any generated project.

    deploy/k8s/configmap.yaml     non-secret settings (STORE, BROKER, NOTIFY, ...)
    deploy/k8s/secret.example.yaml  connection strings, to copy and fill in (never commit the real one)
    deploy/k8s/web.yaml           Deployment + Service: the HTTP API and topic consumers, scalable
    deploy/k8s/scheduler.yaml     Deployment with exactly one replica: runs the scheduled flows
    deploy/k8s/hpa.yaml           autoscaling for the web Deployment
    deploy/k8s/frontend.yaml      the web app (nginx: the React build, /api forwarded to the API)
    deploy/k8s/ingress.yaml       HTTP(S) entry point (GKE Ingress with a managed certificate)
    deploy/DEPLOY.md              GKE step by step, then EKS, AKS and Cloud Run

Why two Deployments: every instance of the app can serve HTTP and consume
topics side by side (RabbitMQ gives each message to one of them), but the
scheduler must run exactly once, or a nightly batch would run once per
replica. RUN_SCHEDULER=0 on web, 1 on the single scheduler replica.
"""

from danta.codegen.project.common import snake
from danta.codegen.project.infra import needs


def _labels(name, role):
    return f'app.kubernetes.io/name: {name}\n    app.kubernetes.io/component: {role}'


def manifests(system, port, image_hint):
    name = system.name
    n = needs(system)
    has_schedules = any(f.trigger().source == 'schedule' for f in system.flows)
    config = {'HOST': '0.0.0.0', 'PORT': str(port), 'ADMIN_API': '0'}
    secret = {}
    if n['mongo']:
        config.update(STORE='mongo', MONGO_DB=snake(name))
        secret['MONGO_URL'] = 'mongodb+srv://USER:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true'
    if n['rabbitmq']:
        config['BROKER'] = 'rabbitmq'
        secret['RABBITMQ_URL'] = 'amqps://USER:PASSWORD@HOST/VHOST'
    if n['mailpit']:
        config.update(NOTIFY='smtp', SMTP_HOST='smtp.sendgrid.net', SMTP_PORT='587', SMTP_FROM=f'{name}@example.com')
        secret.update(SMTP_USER='apikey', SMTP_PASSWORD='YOUR_SMTP_PASSWORD')
    env_from = [f'            - configMapRef:\n                name: {name}-config']
    if secret:
        env_from.append(f'            - secretRef:\n                name: {name}-secrets')
    env_from = '\n'.join(env_from)

    def deployment(role, replicas, run_scheduler):
        probe = (f'          readinessProbe:\n            tcpSocket:\n              port: {port}\n'
                 f'            initialDelaySeconds: 5\n            periodSeconds: 10\n'
                 f'          livenessProbe:\n            tcpSocket:\n              port: {port}\n'
                 f'            initialDelaySeconds: 30\n            periodSeconds: 20\n')
        return f'''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}-{role}
  labels:
    {_labels(name, role)}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      {_labels(name, role).replace(chr(10) + '    ', chr(10) + '      ')}
  template:
    metadata:
      labels:
        {_labels(name, role).replace(chr(10) + '    ', chr(10) + '        ')}
    spec:
      containers:
        - name: app
          image: {image_hint}
          ports:
            - containerPort: {port}
          envFrom:
{env_from}
          env:
            - name: RUN_SCHEDULER
              value: "{run_scheduler}"
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              memory: 512Mi
{probe}'''

    files = {
        'deploy/k8s/configmap.yaml': f'''apiVersion: v1
kind: ConfigMap
metadata:
  name: {name}-config
data:
''' + ''.join(f'  {k}: "{v}"\n' for k, v in config.items()),
        'deploy/k8s/web.yaml': deployment('web', 2, 0) + f'''---
apiVersion: v1
kind: Service
metadata:
  name: {name}
  labels:
    {_labels(name, 'web')}
spec:
  selector:
    {_labels(name, 'web')}
  ports:
    - port: 80
      targetPort: {port}
''',
        'deploy/k8s/hpa.yaml': f'''apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {name}-web
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {name}-web
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
''',
        'deploy/k8s/ingress.yaml': f'''# GKE: a global HTTP(S) load balancer with a Google-managed certificate.
# Replace api.example.com with your domain and point its DNS at the Ingress address.
apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: {name}-cert
spec:
  domains:
    - api.example.com
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {name}
  annotations:
    kubernetes.io/ingress.class: gce
    networking.gke.io/managed-certificates: {name}-cert
spec:
  defaultBackend:
    service:
      name: {name}
      port:
        number: 80
''',
    }
    if secret:
        files['deploy/k8s/secret.example.yaml'] = f'''# Copy to secret.yaml, fill in, and apply. Never commit the filled-in file.
# Better still, keep these in Secret Manager and sync them with the Secret Store CSI driver.
apiVersion: v1
kind: Secret
metadata:
  name: {name}-secrets
type: Opaque
stringData:
''' + ''.join(f'  {k}: "{v}"\n' for k, v in secret.items())
    if has_schedules:
        files['deploy/k8s/scheduler.yaml'] = deployment('scheduler', 1, 1)
    if system.screens:
        files['deploy/k8s/frontend.yaml'] = f'''# The web app: nginx serves the React build and forwards /api/* to the API Service.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}-frontend
  labels:
    {_labels(name, 'frontend')}
spec:
  replicas: 2
  selector:
    matchLabels:
      {_labels(name, 'frontend').replace(chr(10) + '    ', chr(10) + '      ')}
  template:
    metadata:
      labels:
        {_labels(name, 'frontend').replace(chr(10) + '    ', chr(10) + '        ')}
    spec:
      containers:
        - name: web
          image: WEB_IMAGE
          ports:
            - containerPort: 80
          env:
            - name: API_URL
              value: "http://{name}"
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: 80
---
apiVersion: v1
kind: Service
metadata:
  name: {name}-frontend
  labels:
    {_labels(name, 'frontend')}
spec:
  selector:
    {_labels(name, 'frontend')}
  ports:
    - port: 80
      targetPort: 80
'''
        files['deploy/k8s/ingress.yaml'] = files['deploy/k8s/ingress.yaml'].replace(
            f'      name: {name}\n      port:', f'      name: {name}-frontend\n      port:').replace(
            '# Replace api.example.com', '# The web app answers every path; it forwards /api/* to the API.\n# Replace api.example.com')
    files['deploy/DEPLOY.md'] = _guide(system, port, n, has_schedules, bool(secret))
    return files


def _guide(system, port, n, has_schedules, has_secret):
    name = system.name
    ui = bool(system.screens)
    apply = ['configmap.yaml'] + (['secret.yaml'] if has_secret else []) + ['web.yaml', 'hpa.yaml'] + \
        (['scheduler.yaml'] if has_schedules else []) + (['frontend.yaml'] if ui else []) + ['ingress.yaml']
    services = []
    if n['mongo']:
        services.append('| MongoDB | MongoDB Atlas on GCP (same region), or the MongoDB Community Operator on the cluster | `MONGO_URL` secret |')
    if n['rabbitmq']:
        services.append('| RabbitMQ | CloudAMQP, or the RabbitMQ Cluster Operator on the cluster | `RABBITMQ_URL` secret |')
    if n['mailpit']:
        services.append('| Email | an SMTP relay (SendGrid, Mailgun, Amazon SES); Mailpit is for local use only | `SMTP_HOST`/`SMTP_PORT`/`SMTP_FROM` in the ConfigMap, `SMTP_USER`/`SMTP_PASSWORD` secret |')
    lines = [f'# Deploying {name}', '',
             'The app is one container image, configured by environment variables. Locally, `docker compose up`',
             'runs it with its infrastructure. In the cloud the same image runs on Kubernetes, and the',
             'infrastructure comes from managed services.', '',
             '## What runs where', '',
             '| Piece | In the cloud | Configured by |', '|---|---|---|',
             f'| the app | Kubernetes: `{name}-web` (HTTP API and topic consumers, 2–10 replicas)'
             + (f' and `{name}-scheduler` (exactly 1 replica, runs the scheduled flows)' if has_schedules else '')
             + ' | `deploy/k8s/*.yaml` |',
             *([f'| the web app | Kubernetes: `{name}-frontend` (nginx with the React build; forwards `/api` to the API) '
                '| `deploy/k8s/frontend.yaml` |'] if ui else []),
             *services, '']
    if has_schedules:
        lines += ['> The scheduler has its own Deployment with one replica so that scheduled flows run exactly',
                  '> once. The web replicas set `RUN_SCHEDULER=0`; scale them freely.', '']
    lines += ['## Google Cloud (GKE)', '', '1. **Set up the project and an image repository**', '', '```bash',
              'export PROJECT=my-gcp-project REGION=europe-west1',
              'gcloud config set project $PROJECT',
              'gcloud services enable container.googleapis.com artifactregistry.googleapis.com',
              'gcloud artifacts repositories create apps --repository-format=docker --location=$REGION', '```', '',
              '2. **Build and push the image**', '', '```bash',
              f'export IMAGE=$REGION-docker.pkg.dev/$PROJECT/apps/{name}:0.1.0',
              'gcloud auth configure-docker $REGION-docker.pkg.dev',
              'docker build --platform linux/amd64 -t $IMAGE . && docker push $IMAGE',
              *([f'export WEB_IMAGE=$REGION-docker.pkg.dev/$PROJECT/apps/{name}-web:0.1.0',
                 'docker build --platform linux/amd64 -t $WEB_IMAGE web && docker push $WEB_IMAGE'] if ui else []),
              '```', '',
              '3. **Create a cluster** (Autopilot manages nodes for you)', '', '```bash',
              f'gcloud container clusters create-auto {name} --region $REGION',
              f'gcloud container clusters get-credentials {name} --region $REGION', '```', '']
    step = 4
    if services:
        lines += [f'{step}. **Provision the infrastructure** from the table above, and note each connection string.', '']
        step += 1
    if has_secret:
        lines += [f'{step}. **Store the connection strings**', '', '```bash',
                  'cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml   # fill it in; do not commit it', '```', '']
        step += 1
    lines += [f'{step}. **Point the manifests at your image and domain**: replace `IMAGE` in `web.yaml`'
              + (' and `scheduler.yaml`' if has_schedules else '')
              + (', `WEB_IMAGE` in `frontend.yaml`' if ui else '') + ', and `api.example.com` in `ingress.yaml`.', '',
              f'{step + 1}. **Deploy**', '', '```bash',
              *[f'kubectl apply -f deploy/k8s/{f}' for f in apply],
              f'kubectl get ingress {name}      # the external address; DNS for your domain points here', '```', '',
              (f'The web app is then at `https://api.example.com/`; it calls the API under `/api`. For the'
               f' Swagger UI, `kubectl port-forward svc/{name} 8080:80` and open http://localhost:8080/docs.' if ui else
               'The API and its Swagger UI are then at `https://api.example.com/docs`.'), '',
              '## Other clouds', '',
              'The manifests are plain Kubernetes, except `ingress.yaml`, which uses GKE\'s Ingress class and',
              'managed certificate.', '',
              '| | Images | Cluster | Ingress | Managed infrastructure |', '|---|---|---|---|---|',
              '| **AWS (EKS)** | ECR | `eksctl create cluster` | AWS Load Balancer Controller (`alb` IngressClass), ACM certificate |'
              ' MongoDB Atlas on AWS; Amazon MQ for RabbitMQ; Amazon SES SMTP |',
              '| **Azure (AKS)** | ACR (`az aks update --attach-acr`) | `az aks create` | Application Gateway for Containers or ingress-nginx |'
              ' MongoDB Atlas on Azure; CloudAMQP; Azure Communication Services email |',
              '| **Google Cloud Run** | Artifact Registry | none: `gcloud run deploy --image $IMAGE` |'
              ' built in | Set `--min-instances=1 --no-cpu-throttling` so topic consumers keep running;'
              ' deploy the same image twice: the API with `RUN_SCHEDULER=0`, and a scheduler service with'
              ' `RUN_SCHEDULER=1 --min-instances=1 --max-instances=1` |', '',
              'Whichever you use: keep secrets in the platform\'s secret manager, keep `ADMIN_API=0` in',
              'production, and run exactly one scheduler.', '']
    return '\n'.join(lines)
