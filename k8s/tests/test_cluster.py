#!/usr/bin/env python3
"""
K8s Cluster Test Suite — kribaat.com
=====================================
Run BEFORE every push to GitHub that touches k8s/ files.

Usage (on the cluster node):
  python3 k8s/tests/test_cluster.py

Usage (from dev machine via SSH):
  ssh -i Kribaat.pem ubuntu@43.152.233.234 'python3 -' < k8s/tests/test_cluster.py

Exit codes:
  0  All tests passed
  1  One or more tests FAILED — do NOT push
"""
import subprocess, sys, json

PASS = FAIL = WARN = 0
G, R, Y, B, N = '\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[0m'


# ── helpers ─────────────────────────────────────────────────────────────────

def kube(jsonpath, resource, ns='chatplatform'):
    r = subprocess.run(
        ['kubectl', '-n', ns, 'get', *resource.split(),
         '-o', f'jsonpath={jsonpath}'],
        capture_output=True, text=True
    )
    return r.stdout.strip()


def kexec(selector, cmd, ns='chatplatform'):
    r = subprocess.run(
        ['kubectl', '-n', ns, 'exec', selector, '--', 'sh', '-c', cmd],
        capture_output=True, text=True
    )
    return r.stdout.strip()


def curl_code(url):
    r = subprocess.run(['curl', '-so', '/dev/null', '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    return r.stdout.strip()


def curl_ms(url):
    r = subprocess.run(['curl', '-so', '/dev/null', '-w', '%{time_total}', url],
                       capture_output=True, text=True)
    try:
        return int(float(r.stdout.strip()) * 1000)
    except ValueError:
        return 9999


def image_tag(img):
    return img.split(':')[-1] if ':' in img else img


def p(msg):
    global PASS; PASS += 1
    print(f'{G}  PASS{N} {msg}')


def f(msg):
    global FAIL; FAIL += 1
    print(f'{R}  FAIL{N} {msg}')


def w(msg):
    global WARN; WARN += 1
    print(f'{Y}  WARN{N} {msg}')


def s(title):
    print(f'\n{B}=== {title} ==={N}')


def eq(desc, actual, expected):
    if actual == expected:
        p(desc)
    else:
        f(f'{desc}\n       got:  "{actual}"\n       want: "{expected}"')


def has(desc, val):
    if val and val not in ('null', '{}', '[]', ''):
        p(desc)
    else:
        f(f'{desc} — missing / empty')


def inc(desc, haystack, needle):
    if needle in haystack:
        p(desc)
    else:
        f(f'{desc} — "{needle}" not found')


def exc(desc, haystack, needle):
    if needle not in haystack:
        p(desc)
    else:
        f(f'{desc} — "{needle}" should NOT be present')


# ── image tag consistency helper ─────────────────────────────────────────────
# CI only builds new images when app code changes.
# Config-only commits (k8s/*.yaml) reuse the previous image tag.
# So we read the EXPECTED tag from the deployment manifest itself,
# then assert all deployments use the SAME tag (no mixing of versions).

def get_all_tags():
    tags = {}
    for dep in ['backend', 'celery-beat', 'celery-worker']:
        img = kube('{.spec.template.spec.containers[0].image}', f'deployment {dep}')
        tags[dep] = image_tag(img)
    img = kube('{.spec.template.spec.containers[0].image}', 'deployment frontend')
    tags['frontend'] = image_tag(img)
    return tags


# ── tests ────────────────────────────────────────────────────────────────────

print(f'\n╔{"═"*44}╗')
print(f'║  K8s Cluster Test Suite — kribaat.com    ║')
print(f'╚{"═"*44}╝')

# ────────────────────────────────────────────────
s('1. ARGOCD — SYNC, HEALTH & CONFIGURATION')
# ────────────────────────────────────────────────
sync    = kube('{.status.sync.status}',   'application chatplatform', 'argocd')
health  = kube('{.status.health.status}', 'application chatplatform', 'argocd')
conds   = kube('{.status.conditions}',    'application chatplatform', 'argocd')
excl    = kube('{.spec.source.directory.exclude}', 'application chatplatform', 'argocd')
selfh   = kube('{.spec.syncPolicy.automated.selfHeal}', 'application chatplatform', 'argocd')
prune   = kube('{.spec.syncPolicy.automated.prune}', 'application chatplatform', 'argocd')
rev     = kube('{.status.sync.revision}', 'application chatplatform', 'argocd')

eq('ArgoCD Synced', sync, 'Synced')
if health == 'Healthy':
    p('ArgoCD Healthy')
else:
    w(f'ArgoCD health={health} — may be mid-rollout, re-run after deploy settles')
if not conds or conds == 'null':
    p('No ArgoCD error conditions')
else:
    f(f'ArgoCD conditions: {conds[:150]}')
inc('ArgoCD excludes kustomization.yaml (directory-mode config file, not a K8s manifest)', excl, 'kustomization.yaml')
eq('ArgoCD selfHeal=true', selfh, 'true')
eq('ArgoCD prune=true', prune, 'true')
print(f'  Tracking revision: {rev[:7]}')

# ────────────────────────────────────────────────
s('2. ALL PODS RUNNING & STABLE')
# ────────────────────────────────────────────────
pods_raw = subprocess.run(
    ['kubectl', '-n', 'chatplatform', 'get', 'pods', '--no-headers'],
    capture_output=True, text=True
).stdout

for comp in ['backend', 'celery-worker', 'celery-beat', 'frontend']:
    running = [l for l in pods_raw.splitlines()
               if l.startswith(comp) and 'Completed' not in l and 'Terminating' not in l]
    if not running:
        f(f'{comp} — no Running pod (Terminating = deploy in progress, re-run later)')
        continue
    status   = running[0].split()[2]
    restarts = running[0].split()[3]
    eq(f'{comp} Running', status, 'Running')
    if restarts == '0':
        p(f'{comp} 0 restarts')
    else:
        w(f'{comp} has {restarts} restart(s) — investigate if > 2')

for ss in ['postgres-0', 'redis-0']:
    phase = kube('{.status.phase}', f'pod {ss}')
    eq(f'{ss} Running', phase, 'Running')

# ────────────────────────────────────────────────
s('3. IMAGE TAG CONSISTENCY (all components same version)')
# ────────────────────────────────────────────────
# NOTE: ArgoCD revision != image tag on config-only commits.
# CI only builds a new image when app code changes (backend/ or frontend/).
# We assert all app components use the SAME image tag (no mixed versions).
tags = get_all_tags()
backend_tag = tags.get('backend', 'unknown')
print(f'  Current image tag: {backend_tag}')
for name, tag in tags.items():
    eq(f'{name} tag consistent ({tag})', tag, backend_tag)

# Also check migrate-job uses same tag (it must run same migrations as deployed code)
mimg = kube('{.spec.template.spec.containers[0].image}', 'job django-migrate')
if mimg:
    eq(f'migrate-job tag matches backend ({backend_tag})', image_tag(mimg), backend_tag)
else:
    w('migrate-job cleaned up by ttl (normal after ~5min)')

# ────────────────────────────────────────────────
s('4. ZERO-DOWNTIME DEPLOYMENT STRATEGIES')
# ────────────────────────────────────────────────
for dep in ['backend', 'celery-worker', 'frontend']:
    eq(f'{dep} strategy=RollingUpdate', kube('{.spec.strategy.type}', f'deployment {dep}'), 'RollingUpdate')
    eq(f'{dep} maxUnavailable=0 (no traffic gap)', kube('{.spec.strategy.rollingUpdate.maxUnavailable}', f'deployment {dep}'), '0')
    eq(f'{dep} maxSurge=1 (new pod starts first)', kube('{.spec.strategy.rollingUpdate.maxSurge}', f'deployment {dep}'), '1')

# celery-beat MUST be Recreate — duplicate beat processes double-fire every scheduled task
eq('celery-beat strategy=Recreate (singleton — duplicate would double-fire tasks)',
   kube('{.spec.strategy.type}', 'deployment celery-beat'), 'Recreate')

# ────────────────────────────────────────────────
s('5. PRESYNC MIGRATION JOB')
# ────────────────────────────────────────────────
hook = kube(r'{.metadata.annotations.argocd\.argoproj\.io/hook}', 'job django-migrate')
eq('django-migrate has PreSync hook annotation', hook, 'PreSync')
succeeded = kube('{.status.succeeded}', 'job django-migrate')
eq('django-migrate completed successfully', succeeded, '1')
dp = kube(r'{.metadata.annotations.argocd\.argoproj\.io/hook-delete-policy}', 'job django-migrate')
eq('django-migrate delete-policy=BeforeHookCreation', dp, 'BeforeHookCreation')

# ────────────────────────────────────────────────
s('6. GRACEFUL SHUTDOWN (terminationGracePeriodSeconds + preStop)')
# ────────────────────────────────────────────────
eq('backend terminationGracePeriodSeconds=90 (15s drain + 30s gunicorn + headroom)',
   kube('{.spec.template.spec.terminationGracePeriodSeconds}', 'deployment backend'), '90')
eq('frontend terminationGracePeriodSeconds=45',
   kube('{.spec.template.spec.terminationGracePeriodSeconds}', 'deployment frontend'), '45')
eq('celery-worker terminationGracePeriodSeconds=300 (long-running tasks)',
   kube('{.spec.template.spec.terminationGracePeriodSeconds}', 'deployment celery-worker'), '300')

bp = kube('{.spec.template.spec.containers[0].lifecycle.preStop.exec.command}', 'deployment backend')
inc('backend preStop sleeps 15s (Traefik connection drain)', bp, 'sleep 15')

fp = kube('{.spec.template.spec.containers[0].lifecycle.preStop.exec.command}', 'deployment frontend')
inc('frontend preStop runs nginx -s quit (graceful nginx drain)', fp, 'nginx -s quit')

wp = kube('{.spec.template.spec.containers[0].lifecycle.preStop.exec.command}', 'deployment celery-worker')
inc('celery-worker preStop tolerates broker unavailability (|| true)', wp, 'true')

has('postgres preStop flushes WAL (pg_ctl stop -m fast)',
    kube('{.spec.template.spec.containers[0].lifecycle.preStop}', 'statefulset postgres'))
has('redis preStop runs BGSAVE (flush to disk)',
    kube('{.spec.template.spec.containers[0].lifecycle.preStop}', 'statefulset redis'))

# ────────────────────────────────────────────────
s('7. HEALTH PROBES (startup / readiness / liveness)')
# ────────────────────────────────────────────────
for dep in ['backend', 'frontend']:
    for probe in ['startupProbe', 'readinessProbe', 'livenessProbe']:
        val = kube(f'{{.spec.template.spec.containers[0].{probe}}}', f'deployment {dep}')
        has(f'{dep} {probe}', val)

for dep in ['celery-worker', 'celery-beat']:
    val = kube('{.spec.template.spec.containers[0].livenessProbe}', f'deployment {dep}')
    has(f'{dep} livenessProbe', val)

for probe in ['startupProbe', 'readinessProbe', 'livenessProbe']:
    val = kube(f'{{.spec.template.spec.containers[0].{probe}}}', 'statefulset postgres')
    has(f'postgres {probe}', val)

for probe in ['readinessProbe', 'livenessProbe']:
    val = kube(f'{{.spec.template.spec.containers[0].{probe}}}', 'statefulset redis')
    has(f'redis {probe}', val)

# ────────────────────────────────────────────────
s('8. RESOURCE REQUESTS & LIMITS')
# ────────────────────────────────────────────────
eq('backend memory request=512Mi (was 256Mi — caused 120% HPA reading)',
   kube('{.spec.template.spec.containers[0].resources.requests.memory}', 'deployment backend'), '512Mi')
eq('backend memory limit=1Gi',
   kube('{.spec.template.spec.containers[0].resources.limits.memory}', 'deployment backend'), '1Gi')
eq('celery-beat memory request=256Mi',
   kube('{.spec.template.spec.containers[0].resources.requests.memory}', 'deployment celery-beat'), '256Mi')
eq('celery-beat memory limit=512Mi',
   kube('{.spec.template.spec.containers[0].resources.limits.memory}', 'deployment celery-beat'), '512Mi')

# ────────────────────────────────────────────────
s('9. HPA — AUTOSCALER')
# ────────────────────────────────────────────────
eq('backend-hpa minReplicas=1 (pinned — media-pvc is RWO, cannot scale until S3 migration)',
   kube('{.spec.minReplicas}', 'hpa backend-hpa'), '1')
eq('backend-hpa maxReplicas=1',
   kube('{.spec.maxReplicas}', 'hpa backend-hpa'), '1')
eq('frontend-hpa minReplicas=2 (HA — 2 replicas always)',
   kube('{.spec.minReplicas}', 'hpa frontend-hpa'), '2')
eq('frontend-hpa maxReplicas=5',
   kube('{.spec.maxReplicas}', 'hpa frontend-hpa'), '5')
fm = kube('{.spec.metrics[*].resource.name}', 'hpa frontend-hpa')
inc('frontend-hpa monitors CPU', fm, 'cpu')
inc('frontend-hpa monitors memory', fm, 'memory')

# ────────────────────────────────────────────────
s('10. CONFIGMAP SECURITY')
# ────────────────────────────────────────────────
ah = kube('{.data.ALLOWED_HOSTS}', 'configmap chatplatform-config')
# IMPORTANT: Must remain * — K8s probes hit pod IPs (10.42.x.x) directly.
# Django's ALLOWED_HOSTS has no CIDR support. Security boundary = Traefik.
eq('ALLOWED_HOSTS=* (K8s probe IPs require wildcard — see commit fix history)',
   ah, '*')
eq('DEBUG=False in production',
   kube('{.data.DEBUG}', 'configmap chatplatform-config'), 'False')
cors = kube('{.data.CORS_ALLOWED_ORIGINS}', 'configmap chatplatform-config')
exc('CORS_ALLOWED_ORIGINS has no raw server IP (security)', cors, '43.152.233.234')
inc('CORS_ALLOWED_ORIGINS has https://kribaat.com', cors, 'https://kribaat.com')

# ────────────────────────────────────────────────
s('11. REDIS DATA SAFETY')
# ────────────────────────────────────────────────
policy = kexec('statefulset/redis', 'redis-cli config get maxmemory-policy 2>/dev/null | tail -1')
# volatile-lru only evicts keys with TTL set — protects Celery task queue messages.
# allkeys-lru would evict ANY key including task queue under memory pressure.
eq('Redis maxmemory-policy=volatile-lru (protects Celery task queue from eviction)',
   policy, 'volatile-lru')
aof = kexec('statefulset/redis', 'redis-cli config get appendonly 2>/dev/null | tail -1')
eq('Redis AOF persistence=yes (Celery tasks survive Redis restart)', aof, 'yes')

# ────────────────────────────────────────────────
s('12. ARGOCD INGRESS — NO DEAD ANNOTATIONS')
# ────────────────────────────────────────────────
# Check annotation KEYS directly (not the last-applied-configuration blob
# which is a historical JSON string and may contain old annotation names)
r = subprocess.run(
    ['kubectl', '-n', 'argocd', 'get', 'ingress', 'argocd-server',
     '-o', 'jsonpath={.metadata.annotations}'],
    capture_output=True, text=True
)
try:
    ann_keys = list(json.loads(r.stdout.strip()).keys())
except Exception:
    ann_keys = []
nginx_keys = [k for k in ann_keys if k.startswith('nginx.ingress.kubernetes.io')]
if not nginx_keys:
    p('ArgoCD ingress: no live nginx annotations (cluster runs Traefik)')
else:
    f(f'ArgoCD ingress: nginx annotations still present as live keys: {nginx_keys}')
traefik_tls = 'traefik.ingress.kubernetes.io/router.tls' in ann_keys
if traefik_tls:
    p('ArgoCD ingress: Traefik TLS annotation present')
else:
    f('ArgoCD ingress: Traefik TLS annotation missing')

# ────────────────────────────────────────────────
s('13. LIVE SITE END-TO-END')
# ────────────────────────────────────────────────
eq('kribaat.com → HTTP 200', curl_code('https://kribaat.com'), '200')
eq('API /health/ → HTTP 200', curl_code('https://kribaat.com/api/health/'), '200')
ms = curl_ms('https://kribaat.com')
if ms < 3000:
    p(f'Response time {ms}ms < 3s')
else:
    w(f'Response time {ms}ms (slow — investigate if persistent)')

# Django is actually serving (not 502 from gunicorn)
api_code = curl_code('https://kribaat.com/api/health/')
eq('API health returns 200 (gunicorn + Django up)', api_code, '200')

# ────────────────────────────────────────────────
s('14. REPLICA COUNTS STABLE (no pending pods)')
# ────────────────────────────────────────────────
for dep in ['backend', 'celery-worker', 'celery-beat']:
    ready  = kube('{.status.readyReplicas}', f'deployment {dep}')
    desired = kube('{.spec.replicas}', f'deployment {dep}')
    eq(f'{dep} readyReplicas={desired}', ready, desired)

fr = kube('{.status.readyReplicas}', 'deployment frontend')
fd = kube('{.status.replicas}', 'deployment frontend')
if fr and int(fr) >= 2:
    p(f'frontend {fr} replicas ready (min 2 for HA)')
else:
    f(f'frontend only {fr} replicas ready (want >= 2)')

# ── results ──────────────────────────────────────────────────────────────────
print(f'\n╔{"═"*44}╗')
print(f'║  PASS: {PASS:<5}  WARN: {WARN:<5}  FAIL: {FAIL:<5}    ║')
print(f'╚{"═"*44}╝')

if FAIL > 0:
    print(f'\n{R}BLOCKED — {FAIL} test(s) failed.{N}')
    print(f'{R}Fix the issues above before pushing to GitHub.{N}')
    sys.exit(1)
elif WARN > 0:
    print(f'\n{Y}PASS WITH {WARN} WARNING(S) — review before pushing.{N}')
    sys.exit(0)
else:
    print(f'\n{G}ALL {PASS} TESTS PASSED — safe to push to GitHub.{N}')
    sys.exit(0)
