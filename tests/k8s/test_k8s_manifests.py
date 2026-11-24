"""K8s base: the manifests fit together (no cluster needed).

Checks the addresses in k8s/apnea-config.yaml against the Kafka / PostgreSQL of k8s/base/,
the 5 topics against docker-compose.yml and kafka/schemas/, the region labels, and that the
device-simulator image is built from git only.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
K8S = ROOT / "k8s"
TOPICS = {"raw-signals", "apnea-events", "night-results", "alerts", "carbon-signal"}


def docs(path):
    return [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]


def find(path, kind, name=None):
    found = [d for d in docs(path) if d["kind"] == kind
             and (name is None or d["metadata"]["name"] == name)]
    assert found, f"no {kind} {name or ''} in {path.relative_to(ROOT)}"
    return found


def config():
    return find(K8S / "apnea-config.yaml", "ConfigMap", "apnea-config")[0]["data"]


# ---------------------------------------------------------------- Kafka


def test_kafka_bootstrap_is_the_strimzi_service():
    kafka = find(K8S / "base" / "kafka.yaml", "Kafka")[0]
    listener = next(l for l in kafka["spec"]["kafka"]["listeners"] if not l["tls"])
    expected = f'{kafka["metadata"]["name"]}-kafka-bootstrap:{listener["port"]}'
    assert config()["KAFKA_BOOTSTRAP"] == expected


def test_node_pool_belongs_to_the_cluster():
    kafka = find(K8S / "base" / "kafka.yaml", "Kafka")[0]["metadata"]["name"]
    pool = find(K8S / "base" / "kafka.yaml", "KafkaNodePool")[0]
    assert pool["metadata"]["labels"]["strimzi.io/cluster"] == kafka
    assert set(pool["spec"]["roles"]) == {"controller", "broker"}


def test_the_5_topics():
    kafka = find(K8S / "base" / "kafka.yaml", "Kafka")[0]["metadata"]["name"]
    topics = {t["metadata"]["name"]: t for t in find(K8S / "base" / "kafka-topics.yaml", "KafkaTopic")}
    assert set(topics) == TOPICS
    for t in topics.values():
        assert t["metadata"]["labels"]["strimzi.io/cluster"] == kafka
        assert t["spec"]["replicas"] == 1                      # 1 broker
    assert topics["raw-signals"]["spec"]["partitions"] == 3   # HPA 1-3 detector pods
    hpa = find(K8S / "apnea-detector.yaml", "HorizontalPodAutoscaler")[0]
    assert hpa["spec"]["maxReplicas"] <= topics["raw-signals"]["spec"]["partitions"]


def test_topics_same_as_docker_compose_and_schemas():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    in_compose = dict(re.findall(r"--topic (\S+)\s+--partitions (\d+)", compose))
    topics = {t["metadata"]["name"]: t["spec"]["partitions"]
              for t in find(K8S / "base" / "kafka-topics.yaml", "KafkaTopic")}
    assert {k: int(v) for k, v in in_compose.items()} == topics
    schemas = {p.name.removesuffix("-value.schema.json")
               for p in (ROOT / "kafka" / "schemas").glob("*-value.schema.json")}
    assert schemas == TOPICS


# ---------------------------------------------------------------- PostgreSQL


def test_database_urls_point_to_the_postgres_service():
    service = find(K8S / "base" / "postgres.yaml", "Service", "postgres")[0]
    port = service["spec"]["ports"][0]["port"]
    sts = find(K8S / "base" / "postgres.yaml", "StatefulSet", "postgres")[0]
    env = {e["name"]: e.get("value") for e in sts["spec"]["template"]["spec"]["containers"][0]["env"]}
    secret = find(K8S / "apnea-config.yaml", "Secret", "apnea-db")[0]["stringData"]
    assert secret
    for service_name, url in secret.items():
        u = urlparse(url)
        assert (u.hostname, u.port) == ("postgres", port), service_name
        assert u.path == "/" + env["POSTGRES_DB"], service_name


def test_db_init_is_mounted():
    spec = find(K8S / "base" / "postgres.yaml", "StatefulSet", "postgres")[0]["spec"]["template"]["spec"]
    volume = next(v for v in spec["volumes"] if v["name"] == "db-init")
    assert volume["configMap"]["name"] == "db-init"
    mounts = {m["name"]: m["mountPath"] for m in spec["containers"][0]["volumeMounts"]}
    assert mounts["db-init"] == "/docker-entrypoint-initdb.d"
    # install.sh makes the ConfigMap from the folder, and the folder has the SQL files
    assert "create configmap db-init --from-file=db/init/" in (K8S / "base" / "install.sh").read_text()
    assert sorted(p.name for p in (ROOT / "db" / "init").glob("*.sql"))


# ---------------------------------------------------------------- nodes


def test_kind_nodes_have_the_3_regions():
    cluster = docs(K8S / "kind" / "cluster.yaml")[0]
    regions = [n.get("labels", {}).get("region") for n in cluster["nodes"] if n["role"] == "worker"]
    assert sorted(regions) == ["AT", "NO", "PL"]        # "NO" must stay a string, not False


def test_detector_prefers_a_known_region():
    dep = find(K8S / "apnea-detector.yaml", "Deployment")[0]
    terms = dep["spec"]["template"]["spec"]["affinity"]["nodeAffinity"][
        "preferredDuringSchedulingIgnoredDuringExecution"]
    expr = terms[0]["preference"]["matchExpressions"][0]
    assert expr["key"] == "region" and set(expr["values"]) <= {"AT", "NO", "PL"}


# ---------------------------------------------------------------- device-simulator


def test_simulator_job_reads_the_shared_config():
    job = find(K8S / "jobs" / "device-simulator.yaml", "Job")[0]
    assert job["spec"]["backoffLimit"] == 0                      # never send a night twice
    pod = job["spec"]["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    for c in pod["initContainers"] + pod["containers"]:
        assert {"configMapRef": {"name": "apnea-config"}} in c["envFrom"]
        assert c["image"] == "device-simulator:dev"


def test_simulator_image_is_built_from_git_only():
    dockerfile = (ROOT / "services" / "device-simulator" / "Dockerfile").read_text(encoding="utf-8")
    copies = [l.split()[1:] for l in dockerfile.splitlines() if l.startswith("COPY")]
    sources = [c[0] for c in copies if not c[0].startswith("--from")]
    # kafka/messages/ is ignored by git, so it must come from the build stage
    assert not any(s.startswith("kafka/messages") for s in sources)
    assert "data/03_to_kafka_messages.py" in dockerfile
    assert any(c[0] == "--from=messages" for c in copies)
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for s in sources:
        assert not any(s.startswith(i.rstrip("/")) for i in ignored), s
