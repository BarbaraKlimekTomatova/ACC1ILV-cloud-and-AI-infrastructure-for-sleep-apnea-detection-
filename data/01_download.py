"""Download the PhysioNet nights we need and keep only what the home device measures.

Usage:
    pip install -r data/requirements.txt
    python data/01_download.py                  # all 33 nights (~15 min, ~1.3 GB passes through, ~20 MB stays)
    python data/01_download.py ucddb002 a01r    # only these nights (for a quick test)

For every night it:
  1. downloads the original files into a temporary folder,
  2. keeps 4 signals: spo2, flow (nose/mouth airflow), thorax, abdomen,
  3. downsamples them (spo2 1 Hz, breathing 4 Hz),
  4. keeps the apnea labels (per minute) and the scored events,
  5. saves one small compressed file data/raw/<night>.npz (~0.5 MB),
  6. deletes the big original files.
The .npz files are small enough to commit to git.

Datasets:
  UCDDB (ucddb002 ... ucddb028)  25 adults, training + 5 demo nights
  Apnea-ECG (a01r ... c03r)      8 nights with SpO2 + breathing, F1 test
"""

import re
import sys
import tempfile
import urllib.error
import urllib.request
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np

UCDDB_URL = "https://physionet.org/files/ucddb/1.0.0"
UCDDB = ["ucddb002", "ucddb003", "ucddb005", "ucddb006", "ucddb007",
         "ucddb008", "ucddb009", "ucddb010", "ucddb011", "ucddb012",
         "ucddb013", "ucddb014", "ucddb015", "ucddb017", "ucddb018",
         "ucddb019", "ucddb020", "ucddb021", "ucddb022", "ucddb023",
         "ucddb024", "ucddb025", "ucddb026", "ucddb027", "ucddb028"]

APNEA_ECG_URL = "https://physionet.org/files/apnea-ecg/1.0.0"
APNEA_ECG = ["a01r", "a02r", "a03r", "a04r", "b01r", "c01r", "c02r", "c03r"]

FS = {"spo2": 1, "flow": 4, "thorax": 4, "abdomen": 4}  # target rates in Hz

# Channel names differ between datasets. First match wins (lower case).
CHANNELS = {
    "spo2": ["spo2", "sao2", "sat"],
    "flow": ["resp n", "flow", "nasal"],
    "thorax": ["resp c", "rib", "thor", "chest"],
    "abdomen": ["resp a", "abdo", "abd"],
}

OUT_DIR = Path(__file__).resolve().parent / "raw"


# ---------------------------------------------------------------- helpers


def fetch(url: str, dest: Path, required=True) -> bool:
    print(f"    get {url.rsplit('/', 1)[-1]}", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except urllib.error.HTTPError as err:
        if err.code == 404 and not required:
            return False
        raise


def pick(channels: dict) -> dict:
    """Map dataset channel names to spo2 / flow / thorax / abdomen."""
    picked = {}
    for sig, patterns in CHANNELS.items():
        for pat in patterns:
            hit = next((n for n in channels
                        if pat in n.lower() and n not in picked.values()), None)
            if hit:
                picked[sig] = hit
                break
    missing = set(FS) - set(picked)
    if missing:
        raise ValueError(f"channels {sorted(missing)} not found in {list(channels)}")
    return picked


def downsample(x, fs_in, fs_out):
    """Average blocks of samples (e.g. 8 Hz -> 1 Hz), ignoring missing values."""
    x = np.asarray(x, float)
    ratio = fs_in / fs_out
    if abs(ratio - round(ratio)) > 1e-9 or ratio < 1:
        t_out = np.arange(int(x.size / ratio)) / fs_out
        return np.interp(t_out, np.arange(x.size) / fs_in, x)
    k = int(round(ratio))
    x = x[: x.size // k * k].reshape(-1, k)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # all-missing block -> NaN
        return np.nanmean(x, axis=1)


def compact(channels: dict) -> dict:
    """Keep 4 signals, downsample, set impossible SpO2 to NaN, cut to full minutes."""
    picked = pick(channels)
    out = {}
    for sig, name in picked.items():
        fs_in, x = channels[name]
        x = np.asarray(x, float)
        if sig == "spo2":
            x = x.copy()
            x[(x < 50) | (x > 100)] = np.nan       # sensor drop-out, not real
        out[sig] = downsample(x, fs_in, FS[sig])
    minutes = min(int(out[s].size / FS[s] // 60) for s in out)
    for s in out:
        out[s] = out[s][: minutes * 60 * FS[s]].astype(np.float16)
    return out, minutes, picked


def read_edf(path: Path):
    """Small EDF reader: returns (start time, {label: (fs, values)}).
    UCDDB .rec files are EDF with a different sampling rate per channel."""
    with open(path, "rb") as f:
        head = f.read(256).decode("latin-1")
        n_rec, rec_dur, ns = int(head[236:244]), float(head[244:252]), int(head[252:256])
        sh = f.read(ns * 256).decode("latin-1")
        col = lambda off, w: [sh[off + i * w: off + (i + 1) * w].strip() for i in range(ns)]
        labels = col(0, 16)
        o = ns * (16 + 80 + 8)
        pmin = np.array(col(o, 8), float)
        pmax = np.array(col(o + 8 * ns, 8), float)
        dmin = np.array(col(o + 16 * ns, 8), float)
        dmax = np.array(col(o + 24 * ns, 8), float)
        nsamp = np.array(col(o + 32 * ns + 80 * ns, 8), int)
        f.seek(int(head[184:192]))
        raw = np.fromfile(f, dtype="<i2")
    if n_rec < 0:
        n_rec = raw.size // nsamp.sum()
    raw = raw[: n_rec * nsamp.sum()].reshape(n_rec, -1)
    d, m, y = (int(v) for v in head[168:176].split("."))
    hh, mm, ss = (int(v) for v in head[176:184].split("."))
    start = datetime(2000 + y if y < 85 else 1900 + y, m, d, hh, mm, ss)
    channels, c = {}, 0
    for i, lab in enumerate(labels):
        dig = raw[:, c: c + nsamp[i]].reshape(-1).astype(float)
        c += nsamp[i]
        gain = (pmax[i] - pmin[i]) / (dmax[i] - dmin[i])
        channels[lab] = (nsamp[i] / rec_dur, (dig - dmin[i]) * gain + pmin[i])
    return start, channels


# ---------------------------------------------------------------- datasets


def ucddb(night: str, tmp: Path) -> dict:
    for suffix in (".rec", "_respevt.txt", "_stage.txt"):
        fetch(f"{UCDDB_URL}/{night}{suffix}", tmp / f"{night}{suffix}")
    start, channels = read_edf(tmp / f"{night}.rec")
    signals, minutes, picked = compact(channels)

    # Events file lines look like:  00:23:43  HYP-C  PB  13.0  94  3  -  -
    t0 = start.hour * 3600 + start.minute * 60 + start.second
    onsets, durations, types = [], [], []
    for line in (tmp / f"{night}_respevt.txt").read_text(errors="replace").splitlines():
        tok = line.split()
        if len(tok) < 3 or not re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", tok[0]):
            continue
        dur = next((float(t) for t in tok[2:] if re.fullmatch(r"\d+(\.\d+)?", t)), None)
        if dur is None:
            continue
        h, m, s = (int(v) for v in tok[0].split(":"))
        onsets.append((h * 3600 + m * 60 + s - t0) % 86400)   # seconds from start
        durations.append(dur)
        types.append(tok[1].upper())

    # A minute is "apnea" if any apnea or hypopnea touches it
    # (APNEA-O/C/M, HYP-O/C/M; periodic breathing PB is not counted).
    apnea = np.zeros(minutes, np.int8)
    for on, dur, typ in zip(onsets, durations, types):
        if typ.startswith(("APNEA", "HYP")):
            apnea[int(on // 60): int((on + dur) // 60) + 1] = 1

    # Sleep stage per 30 s epoch: 0 wake, 1 REM, 2-5 stage 1-4, 8/9 unknown.
    epochs = [int(v) for v in (tmp / f"{night}_stage.txt").read_text().split()
              if v.lstrip("-").isdigit()]
    stage = np.full(minutes, -1, np.int8)
    stage[: min(minutes, len(epochs[::2]))] = epochs[::2][:minutes]

    return dict(signals, apnea=apnea, sleep_stage=stage,
                event_onset_s=np.array(onsets, np.float32),
                event_duration_s=np.array(durations, np.float32),
                event_type=np.array(types, dtype="U8"),
                channels=np.array([f"{k}={v}" for k, v in picked.items()]))


def apnea_ecg(night: str, tmp: Path) -> dict:
    import wfdb

    base = night.rstrip("r")                     # labels belong to a01, not a01r
    fetch(f"{APNEA_ECG_URL}/{night}.hea", tmp / f"{night}.hea")
    fetch(f"{APNEA_ECG_URL}/{night}.dat", tmp / f"{night}.dat")
    ann_rec = night if fetch(f"{APNEA_ECG_URL}/{night}.apn", tmp / f"{night}.apn",
                             required=False) else base
    if ann_rec == base:
        fetch(f"{APNEA_ECG_URL}/{base}.apn", tmp / f"{base}.apn")

    rec = wfdb.rdrecord(str(tmp / night))
    channels = {n: (rec.fs, rec.p_signal[:, i]) for i, n in enumerate(rec.sig_name)}
    signals, minutes, picked = compact(channels)

    ann = wfdb.rdann(str(tmp / ann_rec), "apn")
    apnea = np.full(minutes, -1, np.int8)        # -1 = no label for that minute
    for sample, sym in zip(ann.sample, ann.symbol):
        m = int(round(sample / rec.fs / 60))
        if m < minutes:
            apnea[m] = 1 if sym == "A" else 0

    return dict(signals, apnea=apnea, sleep_stage=np.full(minutes, -1, np.int8),
                channels=np.array([f"{k}={v}" for k, v in picked.items()]))


def main(nights):
    OUT_DIR.mkdir(exist_ok=True)
    for night in nights:
        out = OUT_DIR / f"{night}.npz"
        if out.exists():
            print(f"{night}: already there, skip")
            continue
        print(f"{night}:")
        with tempfile.TemporaryDirectory() as tmp:   # big files are deleted after
            data = ucddb(night, Path(tmp)) if night.startswith("ucddb") \
                else apnea_ecg(night, Path(tmp))
        np.savez_compressed(out, **data)
        print(f"    saved {out.name}  {len(data['apnea'])} min, "
              f"{out.stat().st_size / 1e6:.2f} MB")
    total = sum(f.stat().st_size for f in OUT_DIR.glob("*.npz")) / 1e6
    print(f"done. data/raw/ now has {total:.1f} MB")


if __name__ == "__main__":
    wanted = sys.argv[1:] or UCDDB + APNEA_ECG
    unknown = [n for n in wanted if n not in UCDDB + APNEA_ECG]
    if unknown:
        sys.exit(f"unknown night(s): {unknown}")
    main(wanted)
