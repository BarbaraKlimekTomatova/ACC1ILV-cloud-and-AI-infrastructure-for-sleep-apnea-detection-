"""Tests for services/model-trainer/gate.py (F1 gate):  pytest"""

import sys
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "model-trainer"))
import gate as G  # noqa: E402


def test_below_threshold_is_rejected():
    ok, reason = G.decide(0.75, 0.80)
    assert not ok and "below" in reason


def test_above_threshold_without_old_model_is_approved():
    assert G.decide(0.85, 0.80)[0]


def test_worse_than_model_in_use_is_rejected():
    ok, reason = G.decide(0.85, 0.80, current_f1=0.90)
    assert not ok and "worse" in reason


def test_equal_to_model_in_use_is_approved():
    assert G.decide(0.90, 0.80, current_f1=0.90)[0]


def test_missing_f1_is_rejected():
    assert not G.decide(None, 0.80)[0]


def test_model_file_mode_sets_exit_code_and_github_output(tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    good, bad = tmp_path / "good.joblib", tmp_path / "bad.joblib"
    joblib.dump({"version": "accurate-dev", "metrics": {"f1": 0.91}}, good)
    joblib.dump({"version": "accurate-dev", "metrics": {"f1": 0.50}}, bad)
    assert G.main(["--model-file", str(good), "--threshold", "0.8"]) == G.APPROVED
    assert G.main(["--model-file", str(bad), "--threshold", "0.8"]) == G.REJECTED
    text = out.read_text()
    assert "status=approved" in text and "status=rejected" in text
