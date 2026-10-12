"""In-memory inference service with a deterministic physics fallback layer."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import pandas as pd

from backend.services.diagnostics import (MODE_NAMES, classify_risk, derive_kpis, diagnose,
                                          stress_factors)
from ml.feature_engineering import FEATURE_COLUMNS, engineer_features, physics_modes

logger = logging.getLogger("aura.ml")

MODE_PROB_THRESHOLD = 0.5       # ML mode probability needed to flag a failure mode
RULE_MODE_SCORE = 0.9           # score given to modes found by the rule engine
# Risk floor (0-1) applied when a deterministic rule is breached, so the ML model
# can never report "healthy" for a physically impossible operating point.
PHYSICS_RISK_FLOOR: Dict[str, float] = {"HDF": 0.70, "PWF": 0.70, "OSF": 0.70, "TWF": 0.45}
HEURISTIC_BASE_RISK = 0.05      # fallback risk with no rule breached
HEURISTIC_STRESS_WEIGHT = 0.25  # extra fallback risk scaled by the worst stress factor
HEURISTIC_RULE_RISK = 0.72      # fallback risk when any rule is breached
HEURISTIC_RULE_STEP = 0.08      # extra fallback risk per additional breached rule
MAX_RISK = 0.99


class MLService:
    """Loads artifacts once at startup; predict() never raises for valid input."""

    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = artifact_dir
        self.loaded = False
        self._binary = self._multi = self._scaler = None

    def load(self) -> None:
        try:
            self._binary = joblib.load(self.artifact_dir / "model_binary.joblib")
            self._multi = joblib.load(self.artifact_dir / "model_multiclass.joblib")
            self._scaler = joblib.load(self.artifact_dir / "scaler.joblib")
            self.loaded = True
            logger.info("ML artifacts loaded from %s", self.artifact_dir)
        except (FileNotFoundError, OSError, ValueError) as exc:
            self.loaded = False
            logger.error("Could not load ML artifacts (%s) - physics fallback active", exc)

    def _ml_scores(self, feats: pd.DataFrame) -> tuple[float, Dict[str, float]]:
        x = self._scaler.transform(feats[FEATURE_COLUMNS])
        risk = float(self._binary.predict_proba(x)[0][1])
        probs = self._multi.predict_proba(x)
        scores: Dict[str, float] = {}
        for code, arr in zip(("TWF", "HDF", "PWF", "OSF", "RNF"), probs):
            scores[code] = float(arr[0][1]) if arr.shape[1] > 1 else 0.0
        return risk, scores

    def predict(self, payload: dict) -> dict:
        qtype = payload["type"]
        frame = pd.DataFrame([{
            "type": qtype, "air_temp": payload["air_temperature"],
            "process_temp": payload["process_temperature"], "rpm": payload["rotational_speed"],
            "torque": payload["torque"], "tool_wear": payload["tool_wear"]}])
        feats = engineer_features(frame)
        f = {k: float(feats.iloc[0][k]) for k in FEATURE_COLUMNS}
        rule_modes = physics_modes(qtype, f["temp_delta"], f["rpm"], f["power_w"], f["osi"], f["tool_wear"])
        stress = stress_factors(f["temp_delta"], f["torque"], f["rpm"], f["tool_wear"])

        engine, mode_scores = "ml", {m: RULE_MODE_SCORE for m in rule_modes}
        try:
            if not self.loaded:
                raise RuntimeError("model not loaded")
            risk, ml_scores = self._ml_scores(feats)
            for code, score in ml_scores.items():
                if score >= MODE_PROB_THRESHOLD:
                    mode_scores[code] = max(score, mode_scores.get(code, 0.0))
        except (RuntimeError, ValueError, KeyError, AttributeError) as exc:
            logger.warning("Inference fell back to physics rules: %s", exc)
            engine = "physics-fallback"
            worst = max(s["value"] for s in stress) / 100.0
            risk = (min(MAX_RISK, HEURISTIC_RULE_RISK + HEURISTIC_RULE_STEP * (len(rule_modes) - 1))
                    if rule_modes else HEURISTIC_BASE_RISK + HEURISTIC_STRESS_WEIGHT * worst)

        floor = max((PHYSICS_RISK_FLOOR[m] for m in rule_modes), default=0.0)
        risk = min(MAX_RISK, max(risk, floor))
        modes: List[str] = sorted(mode_scores, key=mode_scores.get, reverse=True)
        primary: Optional[str] = modes[0] if modes else None

        risk_pct = round(risk * 100.0, 1)
        code, label = classify_risk(risk_pct)
        efficiency, rul = derive_kpis(risk, f["tool_wear"])
        return {
            "status_code": code, "status_label": label, "is_failure": code == "CRITICAL",
            "risk_percent": risk_pct, "efficiency_percent": efficiency, "rul_hours": rul,
            "primary_failure_mode": f"{MODE_NAMES[primary]} ({primary})" if primary else None,
            "failure_modes": [f"{MODE_NAMES[m]} ({m})" for m in modes],
            "physics": {"temperature_delta_k": round(f["temp_delta"], 2),
                        "mechanical_power_watts": round(f["power_w"], 1),
                        "overstrain_index": round(f["osi"], 1)},
            "stress_factors": stress,
            "diagnosis": diagnose(primary, modes, risk_pct, f, qtype),
            "engine": engine,
        }
