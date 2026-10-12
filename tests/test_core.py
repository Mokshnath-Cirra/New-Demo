"""Core tests - run with:  pytest -q  (no web server needed)."""
import math
from pathlib import Path

import pandas as pd

from backend.services.diagnostics import classify_risk, derive_kpis
from backend.services.ml_service import MLService
from backend.services.rate_limiter import SlidingWindowLimiter
from ml.feature_engineering import engineer_features, physics_modes

ARTIFACTS = Path(__file__).resolve().parent.parent / "ml" / "artifacts"
NOMINAL = dict(type="M", air_temperature=300, process_temperature=310,
               rotational_speed=1500, torque=40, tool_wear=30)
HDF = dict(type="M", air_temperature=303, process_temperature=308,
           rotational_speed=1250, torque=62, tool_wear=80)


def test_feature_formulas():
    df = pd.DataFrame([{"type": "M", "air_temp": 300, "process_temp": 310, "rpm": 1500, "torque": 40, "tool_wear": 30}])
    f = engineer_features(df).iloc[0]
    assert f["temp_delta"] == 10
    assert math.isclose(f["power_w"], 40 * 2 * math.pi * 1500 / 60)
    assert f["osi"] == 1200


def test_rules_detect_hdf():
    assert "HDF" in physics_modes("M", 5.0, 1250, 8000, 1000, 80)


def test_risk_bands_and_kpis():
    assert classify_risk(20)[0] == "HEALTHY" and classify_risk(50)[0] == "WARNING" and classify_risk(80)[0] == "CRITICAL"
    eff, rul = derive_kpis(0.0, 0)
    assert eff == 98.4 and rul == 120.0
    assert derive_kpis(1.0, 100)[0] == 20.0


def test_fallback_never_crashes_and_flags_hdf():
    svc = MLService(Path("/does/not/exist")); svc.load()
    result = svc.predict(HDF)
    assert result["engine"] == "physics-fallback" and result["status_code"] == "CRITICAL"


def test_ml_inference_if_artifacts_exist():
    svc = MLService(ARTIFACTS); svc.load()
    if not svc.loaded:
        return
    assert svc.predict(NOMINAL)["status_code"] == "HEALTHY"
    assert svc.predict(HDF)["primary_failure_mode"].endswith("(HDF)")


def test_rate_limiter():
    limiter = SlidingWindowLimiter(2)
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a") and limiter.allow("b")
