"""Training pipeline: Random Forest binary + multi-output failure-mode models.

Usage:  python -m ml.train               # always train
        python -m ml.train --if-missing  # train only when artifacts are absent

If data/ai4i2020.csv is not present, a synthetic dataset that follows the
published AI4I failure rules is generated, and metrics.json records
"data_source": "synthetic" so results are never mistaken for the real dataset.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputClassifier
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.feature_engineering import (FEATURE_COLUMNS, MODE_COLUMNS, OSF_LIMITS,
                                    RAW_RENAME, engineer_features, mechanical_power_w)

logger = logging.getLogger("aura.train")
DATA_PATH = ROOT / "data" / "ai4i2020.csv"
ARTIFACT_DIR = ROOT / "ml" / "artifacts"
RANDOM_STATE = 42
TEST_SIZE = 0.20
N_ESTIMATORS = 150
MODE_ESTIMATORS = 100
MAX_DEPTH = 12
SYNTHETIC_ROWS = 10_000


def generate_synthetic_dataset(n: int = SYNTHETIC_ROWS, seed: int = RANDOM_STATE) -> pd.DataFrame:
    """Create an AI4I-like dataset using the dataset's published failure rules."""
    rng = np.random.default_rng(seed)
    qtype = rng.choice(["L", "M", "H"], size=n, p=[0.6, 0.3, 0.1])
    air = np.clip(rng.normal(300.0, 2.0, n), 295.3, 304.5)
    proc = air + 10.0 + rng.normal(0.0, 1.0, n)
    rpm = np.clip(1168 + rng.gamma(2.2, 170.0, n), 1168, 2886)
    # Torque falls as speed rises (constant-power drive) -> realistic power spread
    torque = np.clip(40.0 - 0.02 * (rpm - 1540.0) + rng.normal(0.0, 5.0, n), 3.8, 76.6)
    wear = np.clip(rng.gamma(2.6, 36.0, n), 0, 253).round()
    delta = proc - air
    power = np.array([mechanical_power_w(t, r) for t, r in zip(torque, rpm)])
    osi_limit = np.array([OSF_LIMITS[t] for t in qtype])
    hdf = (delta < 8.6) & (rpm < 1380)
    pwf = (power < 3500) | (power > 9000)
    osf = (wear * torque) > osi_limit
    twf = (wear >= 200) & (wear <= 240) & (rng.random(n) < 0.12)
    rnf = rng.random(n) < 0.001
    df = pd.DataFrame({
        "Type": qtype, "Air temperature [K]": air.round(1), "Process temperature [K]": proc.round(1),
        "Rotational speed [rpm]": rpm.round(0), "Torque [Nm]": torque.round(1), "Tool wear [min]": wear,
        "TWF": twf.astype(int), "HDF": hdf.astype(int), "PWF": pwf.astype(int),
        "OSF": osf.astype(int), "RNF": rnf.astype(int),
    })
    df["Machine failure"] = df[MODE_COLUMNS].max(axis=1)
    return df


def load_dataset() -> Tuple[pd.DataFrame, str]:
    """Return (dataframe, source) where source is 'uci' or 'synthetic'."""
    if DATA_PATH.exists():
        logger.info("Loading dataset from %s", DATA_PATH)
        return pd.read_csv(DATA_PATH), "uci"
    logger.warning("%s not found - generating synthetic AI4I-style data", DATA_PATH)
    return generate_synthetic_dataset(), "synthetic"


def run_training_pipeline() -> Dict:
    raw, source = load_dataset()
    df = raw.rename(columns=RAW_RENAME)
    X = engineer_features(df)
    y_bin = df["failure"].astype(int)
    y_modes = df[MODE_COLUMNS].astype(int)

    X_tr, X_te, yb_tr, yb_te, ym_tr, _ = train_test_split(
        X, y_bin, y_modes, test_size=TEST_SIZE, stratify=y_bin, random_state=RANDOM_STATE)

    scaler = StandardScaler().fit(X_tr)
    Xs_tr, Xs_te = scaler.transform(X_tr), scaler.transform(X_te)

    binary = RandomForestClassifier(n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH,
                                    class_weight="balanced", n_jobs=-1, random_state=RANDOM_STATE)
    binary.fit(Xs_tr, yb_tr)

    multi = MultiOutputClassifier(RandomForestClassifier(
        n_estimators=MODE_ESTIMATORS, max_depth=MAX_DEPTH, class_weight="balanced",
        n_jobs=-1, random_state=RANDOM_STATE))
    multi.fit(Xs_tr, ym_tr)

    pred = binary.predict(Xs_te)
    proba = binary.predict_proba(Xs_te)[:, 1]
    tn, fp, fn, tp = confusion_matrix(yb_te, pred, labels=[0, 1]).ravel()
    metrics = {
        "data_source": source, "train_rows": int(len(X_tr)), "test_rows": int(len(X_te)),
        "accuracy": round(float(accuracy_score(yb_te, pred)), 4),
        "precision": round(float(precision_score(yb_te, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(yb_te, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(yb_te, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(yb_te, proba)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "feature_importance": dict(sorted(
            ((f, round(float(v), 4)) for f, v in zip(FEATURE_COLUMNS, binary.feature_importances_)),
            key=lambda kv: kv[1], reverse=True)),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(binary, ARTIFACT_DIR / "model_binary.joblib")
    joblib.dump(multi, ARTIFACT_DIR / "model_multiclass.joblib")
    joblib.dump(scaler, ARTIFACT_DIR / "scaler.joblib")
    (ARTIFACT_DIR / "feature_names.json").write_text(json.dumps(FEATURE_COLUMNS, indent=2))
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    logger.info("Training complete: %s", {k: metrics[k] for k in ("accuracy", "recall", "roc_auc")})
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] [%(levelname)s] [%(module)s]: %(message)s")
    if "--if-missing" in sys.argv and (ARTIFACT_DIR / "model_binary.joblib").exists():
        logger.info("Artifacts present - skipping training")
    else:
        print(json.dumps(run_training_pipeline(), indent=2))
