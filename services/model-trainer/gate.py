"""F1 gate (UC7 steps 6-7, alternative flow A1, ADR 0005).

A new model version is used only if its F1 on the held-out Apnea-ECG nights is
at least the threshold AND not worse than the version in use now.

    python services/model-trainer/gate.py                       # newest pending accurate row
    python services/model-trainer/gate.py --version accurate-v3
    python services/model-trainer/gate.py --model-file models/model.joblib   # no database (CI)

With the database it sets model_versions.status to 'approved' or 'rejected'
(as DB user model_trainer, who may UPDATE its own table).
Exit code: 0 approved, 1 rejected, 2 nothing to check. In GitHub Actions the
result is also written to $GITHUB_OUTPUT (status=..., version=..., f1=...).
"""

import argparse
import os
import sys

DEFAULT_DB = "postgresql://model_trainer:dev_model_trainer@localhost:5432/sleep_apnea"
DEFAULT_THRESHOLD = 0.80
APPROVED, REJECTED, NOTHING = 0, 1, 2


def decide(f1, threshold, current_f1=None):
    """-> (approved?, reason)"""
    if f1 is None:
        return False, "no F1 stored"
    if f1 < threshold:
        return False, f"F1 {f1:.3f} is below the threshold {threshold:.2f}"
    if current_f1 is not None and f1 < current_f1:
        return False, f"F1 {f1:.3f} is worse than the model in use ({current_f1:.3f})"
    return True, f"F1 {f1:.3f} >= threshold {threshold:.2f}" + (
        f" and >= model in use ({current_f1:.3f})" if current_f1 is not None else "")


# ------------------------------------------------------------------ database
def pending_row(conn, model, version=None):
    """(version, f1) of the row to check, or None."""
    with conn.cursor() as cur:
        if version:
            cur.execute("SELECT version, f1 FROM model_versions WHERE version = %s AND status = 'pending'",
                        (version,))
        else:
            cur.execute("SELECT version, f1 FROM model_versions WHERE model = %s AND status = 'pending' "
                        "ORDER BY trained_at DESC LIMIT 1", (model,))
        return cur.fetchone()


def current_f1(conn, model):
    """F1 of the newest approved version of this model (= the one in use), or None."""
    with conn.cursor() as cur:
        cur.execute("SELECT f1 FROM model_versions WHERE model = %s AND status = 'approved' "
                    "ORDER BY trained_at DESC LIMIT 1", (model,))
        row = cur.fetchone()
    return row[0] if row else None


def set_status(conn, version, status):
    with conn.cursor() as cur:
        cur.execute("UPDATE model_versions SET status = %s WHERE version = %s", (status, version))
    conn.commit()


# ------------------------------------------------------------------ main
def github_output(**values):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="F1 gate for a new model version.")
    p.add_argument("--threshold", type=float,
                   default=float(os.environ.get("F1_THRESHOLD", DEFAULT_THRESHOLD)))
    p.add_argument("--model", default="accurate", choices=["accurate", "fast"])
    p.add_argument("--version", help="check this version (default: newest pending one)")
    p.add_argument("--db-url", default=os.environ.get("DATABASE_URL", DEFAULT_DB))
    p.add_argument("--model-file", help="no database: read the F1 saved in this .joblib file")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)

    if a.model_file:                                  # CI without a database
        import joblib
        bundle = joblib.load(a.model_file)
        version, f1 = bundle.get("version"), bundle.get("metrics", {}).get("f1")
        ok, reason = decide(f1, a.threshold)
    else:
        import psycopg
        with psycopg.connect(a.db_url) as conn:
            row = pending_row(conn, a.model, a.version)
            if row is None:
                print(f"nothing to check: no pending {a.version or a.model} version")
                github_output(status="none")
                return NOTHING
            version, f1 = row
            ok, reason = decide(f1, a.threshold, current_f1(conn, a.model))
            set_status(conn, version, "approved" if ok else "rejected")

    status = "approved" if ok else "rejected"
    print(f"{version}: {status} – {reason}")
    github_output(status=status, version=version, f1=f"{f1:.4f}" if f1 is not None else "")
    return APPROVED if ok else REJECTED


if __name__ == "__main__":
    sys.exit(main())
