"""Domain physics feature engineering, shared by training and live inference.

Every threshold below mirrors the failure definitions of the UCI AI4I 2020
Predictive Maintenance dataset so the model and the rule engine agree.
"""
from __future__ import annotations

import math
from typing import Dict, List

import numpy as np
import pandas as pd

# --- Physical thresholds (named constants, never magic numbers) -----------
SAFE_TEMP_DELTA_K = 8.6        # process-air delta below this impairs cooling
HDF_RPM_LIMIT = 1380.0         # low speed + low delta => heat dissipation failure
POWER_MIN_W = 3500.0           # lower bound of continuous power band
POWER_MAX_W = 9000.0           # upper bound of continuous power band
OSF_LIMITS = {"L": 11000.0, "M": 12000.0, "H": 13000.0}  # overstrain limits, min*Nm
TOOL_WEAR_LIMIT_MIN = 200.0    # start of tool end-of-life zone
TOOL_WEAR_EOL_MIN = 240.0      # end of tool end-of-life zone

QUALITY_ENCODING: Dict[str, int] = {"L": 0, "M": 1, "H": 2}
MODE_COLUMNS: List[str] = ["TWF", "HDF", "PWF", "OSF", "RNF"]

# Column names in the raw UCI CSV -> internal names
RAW_RENAME = {
    "Type": "type",
    "Air temperature [K]": "air_temp",
    "Process temperature [K]": "process_temp",
    "Rotational speed [rpm]": "rpm",
    "Torque [Nm]": "torque",
    "Tool wear [min]": "tool_wear",
    "Machine failure": "failure",
}

FEATURE_COLUMNS: List[str] = [
    "type_encoded", "air_temp", "process_temp", "rpm", "torque", "tool_wear",
    "temp_delta", "power_w", "osi",
]


def mechanical_power_w(torque: float, rpm: float) -> float:
    """P = torque * angular velocity = T * 2*pi*RPM / 60 (Watts)."""
    return torque * 2.0 * math.pi * rpm / 60.0


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add temperature delta, mechanical power and overstrain index.

    Expects columns: type, air_temp, process_temp, rpm, torque, tool_wear.
    """
    out = pd.DataFrame(index=df.index)
    out["type_encoded"] = df["type"].map(QUALITY_ENCODING).fillna(0).astype(int)
    for col in ("air_temp", "process_temp", "rpm", "torque", "tool_wear"):
        out[col] = df[col].astype(float)
    out["temp_delta"] = out["process_temp"] - out["air_temp"]               # Delta T (K)
    out["power_w"] = out["torque"] * 2.0 * np.pi * out["rpm"] / 60.0        # Watts
    out["osi"] = out["tool_wear"] * out["torque"]                           # Overstrain Index
    return out[FEATURE_COLUMNS]


def physics_modes(qtype: str, temp_delta: float, rpm: float, power_w: float,
                  osi: float, tool_wear: float) -> List[str]:
    """Deterministic rule engine: failure modes whose physical trigger is breached."""
    modes: List[str] = []
    if temp_delta < SAFE_TEMP_DELTA_K and rpm < HDF_RPM_LIMIT:
        modes.append("HDF")
    if power_w < POWER_MIN_W or power_w > POWER_MAX_W:
        modes.append("PWF")
    if osi > OSF_LIMITS.get(qtype, OSF_LIMITS["L"]):
        modes.append("OSF")
    if TOOL_WEAR_LIMIT_MIN <= tool_wear <= TOOL_WEAR_EOL_MIN:
        modes.append("TWF")
    return modes
