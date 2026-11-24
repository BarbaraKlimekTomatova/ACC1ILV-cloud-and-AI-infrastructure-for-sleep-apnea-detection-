"""Checks of the UC6 monitoring files: Prometheus rules and the Grafana dashboard "AI & carbon".

No Prometheus is needed. The tests check that the files load and that every metric in a
PromQL query is really exported by one of our services (or is a recording rule of ours),
so a renamed metric breaks the test and not the dashboard."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "monitoring/prometheus/rules/ai-and-carbon.yml"
DASHBOARD = ROOT / "monitoring/grafana/dashboards/ai-and-carbon.json"

PROMQL_WORDS = {"sum", "max", "min", "avg", "count", "rate", "increase", "abs", "by", "without",
                "offset", "and", "or", "unless", "max_over_time", "min_over_time", "avg_over_time",
                "histogram_quantile", "on", "ignoring", "bool"}


def exported_metrics():
    """Names from Counter("..."), Gauge("..."), Histogram("...") in services/ (+ histogram series)."""
    names = set()
    for py in (ROOT / "services").rglob("*.py"):
        for kind, name in re.findall(r'\b(Counter|Gauge|Histogram)\(\s*"([a-z0-9_]+)"', py.read_text()):
            names.add(name)
            if kind == "Counter" and not name.endswith("_total"):
                names.add(name + "_total")       # prometheus_client adds _total to counters
            if kind == "Histogram":
                names |= {name + "_bucket", name + "_sum", name + "_count"}
    return names


def metrics_in(expr):
    """Metric names of a PromQL query: drop label matchers, ranges, by (...) and offsets first."""
    expr = re.sub(r"\{[^}]*\}|\[[^\]]*\]|\bby\s*\([^)]*\)|\boffset\s+\w+", " ", expr)
    words = re.findall(r"[a-zA-Z_:][a-zA-Z0-9_:]*", expr)
    return {w for w in words if w not in PROMQL_WORDS}


@pytest.fixture(scope="module")
def rules():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(RULES.read_text())


@pytest.fixture(scope="module")
def dashboard():
    return json.loads(DASHBOARD.read_text())


def recorded(rules):
    return {r["record"] for g in rules["groups"] for r in g["rules"] if "record" in r}


def test_services_export_the_metrics_we_use():
    names = exported_metrics()
    for m in ("detector_minutes_total", "detector_confidence_bucket", "detector_gco2_total",
              "detector_paused", "triage_nights_total", "triage_llm_gco2_total", "carbon_intensity"):
        assert m in names


def test_every_rule_uses_known_metrics(rules):
    known = exported_metrics() | recorded(rules)
    for group in rules["groups"]:
        for rule in group["rules"]:
            assert metrics_in(rule["expr"]) <= known, rule.get("record") or rule.get("alert")


def test_recording_rules_follow_the_naming_convention(rules):
    for name in recorded(rules):
        assert re.fullmatch(r"[a-z]+:[a-z0-9_]+:\d+[mhd]", name), name


def test_alerts_have_severity_use_case_and_summary(rules):
    alerts = [r for g in rules["groups"] for r in g["rules"] if "alert" in r]
    assert {a["alert"] for a in alerts} >= {"ApneaEventShareDrift", "ModelConfidenceDrift", "ModelLowConfidence"}
    for a in alerts:
        assert a["labels"]["severity"] in ("warning", "critical")
        assert a["labels"]["use_case"].startswith("UC")
        assert a["annotations"]["summary"]


def test_drift_alerts_compare_with_last_week(rules):
    alerts = {r["alert"]: r for g in rules["groups"] for r in g["rules"] if "alert" in r}
    for name in ("ApneaEventShareDrift", "ModelConfidenceDrift"):
        assert "offset 1w" in alerts[name]["expr"]


def test_dashboard_panels_are_valid(dashboard):
    assert dashboard["uid"] == "ai-and-carbon" and dashboard["title"] == "AI & carbon"
    ids = [p["id"] for p in dashboard["panels"]]
    assert len(ids) == len(set(ids))
    for p in dashboard["panels"]:
        if p["type"] == "row":
            continue
        assert p["targets"] and p["datasource"]["uid"] == "${datasource}"
        g = p["gridPos"]
        assert g["x"] + g["w"] <= 24


def test_dashboard_uses_known_metrics(dashboard, rules):
    known = exported_metrics() | recorded(rules)
    for p in dashboard["panels"]:
        for t in p.get("targets", []):
            assert metrics_in(t["expr"]) <= known, (p["title"], t["expr"])


def test_dashboard_shows_what_uc6_asks_for(dashboard):
    exprs = " ".join(t["expr"] for p in dashboard["panels"] for t in p.get("targets", []))
    for needed in ("detector_minutes_total", "triage_nights_total", "confidence", "gco2",
                   "carbon_intensity", "carbon_high_mode"):
        assert needed in exprs
