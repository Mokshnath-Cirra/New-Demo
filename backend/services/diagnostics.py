"""Root-cause explainability, KPI derivation and stress-factor scoring."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ml.feature_engineering import (HDF_RPM_LIMIT, OSF_LIMITS, POWER_MAX_W, POWER_MIN_W,
                                    SAFE_TEMP_DELTA_K, TOOL_WEAR_EOL_MIN, TOOL_WEAR_LIMIT_MIN)

# --- Risk bands (percent) -------------------------------------------------
HEALTHY_MAX_RISK = 35.0
WARNING_MAX_RISK = 65.0
# --- KPI model constants --------------------------------------------------
EFFICIENCY_MIN = 20.0       # efficiency at 100% failure risk
EFFICIENCY_MAX = 98.4       # efficiency at 0% failure risk
RUL_MAX_HOURS = 120.0       # remaining useful life of a fresh, healthy tool/machine
TOOL_WEAR_MAX_MIN = 260.0   # upper end of the tool-wear sensor range
RUL_RISK_EXPONENT = 0.8     # shapes how fast RUL collapses as risk rises
# --- Stress-factor normalisation ranges -----------------------------------
DELTA_T_NO_STRESS_K = 11.2  # delta-T at/above which thermal stress is 0
DELTA_T_FULL_STRESS_K = 7.0 # delta-T at/below which thermal stress is 100
TORQUE_NO_STRESS_NM = 20.0
TORQUE_FULL_STRESS_NM = 65.0
NOMINAL_RPM = 1500.0
RPM_FULL_DEVIATION = 1000.0

MODE_NAMES: Dict[str, str] = {
    "HDF": "Heat Dissipation Failure",
    "PWF": "Power Failure",
    "OSF": "Overstrain Failure",
    "TWF": "Tool Wear Failure",
    "RNF": "Random Failure",
}
MODE_ACTIONS: Dict[str, str] = {
    "HDF": "Reduce load, inspect coolant flow, purge the heat exchanger and verify ambient ventilation.",
    "PWF": "Reduce feed rate, check drive inverter calibration and inspect spindle motor current draw.",
    "OSF": "Lower torque demand or replace the worn tool before resuming the cut.",
    "TWF": "Schedule an immediate cutting-tool replacement and re-qualify the first part.",
    "RNF": "Log the event, run a full sensor sanity check and monitor the next 3 cycles closely.",
}


def classify_risk(risk_percent: float) -> Tuple[str, str]:
    """Map a risk percentage to (status_code, human label)."""
    if risk_percent <= HEALTHY_MAX_RISK:
        return "HEALTHY", "HEALTHY"
    if risk_percent <= WARNING_MAX_RISK:
        return "WARNING", "ELEVATED RISK"
    return "CRITICAL", "HIGH RISK"


def derive_kpis(risk_fraction: float, tool_wear: float) -> Tuple[float, float]:
    """Return (operating efficiency %, estimated remaining useful life in hours)."""
    efficiency = EFFICIENCY_MIN + (EFFICIENCY_MAX - EFFICIENCY_MIN) * (1.0 - risk_fraction)
    wear_left = max(0.0, 1.0 - tool_wear / TOOL_WEAR_MAX_MIN)
    rul = RUL_MAX_HOURS * wear_left * (1.0 - risk_fraction) ** RUL_RISK_EXPONENT
    return round(efficiency, 1), round(rul, 1)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def stress_factors(temp_delta: float, torque: float, rpm: float, tool_wear: float) -> List[dict]:
    """Four 0-100 stress scores that drive the dashboard progress bars."""
    thermal = _clamp01((DELTA_T_NO_STRESS_K - temp_delta) / (DELTA_T_NO_STRESS_K - DELTA_T_FULL_STRESS_K))
    load = _clamp01((torque - TORQUE_NO_STRESS_NM) / (TORQUE_FULL_STRESS_NM - TORQUE_NO_STRESS_NM))
    velocity = _clamp01(abs(rpm - NOMINAL_RPM) / RPM_FULL_DEVIATION)
    wear = _clamp01(tool_wear / TOOL_WEAR_EOL_MIN)
    return [
        {"key": "thermal", "label": "Thermal Differential", "value": round(thermal * 100, 1)},
        {"key": "torque", "label": "Torque Load Strain", "value": round(load * 100, 1)},
        {"key": "velocity", "label": "Velocity Deviation", "value": round(velocity * 100, 1)},
        {"key": "wear", "label": "Tool Wear Stress", "value": round(wear * 100, 1)},
    ]


def _cause_for(mode: str, f: Dict[str, float], qtype: str) -> str:
    if mode == "HDF":
        return (f"Process-air temperature difference is {f['temp_delta']:.1f} K (safe minimum "
                f"{SAFE_TEMP_DELTA_K} K) at only {f['rpm']:.0f} RPM (below {HDF_RPM_LIMIT:.0f}), "
                "so heat cannot be removed fast enough.")
    if mode == "PWF":
        return (f"Mechanical power of {f['power_w']:.0f} W is outside the "
                f"{POWER_MIN_W:.0f}-{POWER_MAX_W:.0f} W continuous operating band.")
    if mode == "OSF":
        return (f"Overstrain index {f['osi']:.0f} min*Nm exceeds the {OSF_LIMITS.get(qtype, OSF_LIMITS['L']):.0f} "
                f"limit for quality class {qtype}.")
    if mode == "TWF":
        return (f"Tool wear of {f['tool_wear']:.0f} min is inside the {TOOL_WEAR_LIMIT_MIN:.0f}-"
                f"{TOOL_WEAR_EOL_MIN:.0f} min end-of-life zone.")
    return "No physical threshold is breached; the model flags a statistically unusual pattern."


def diagnose(primary: Optional[str], modes: List[str], risk_percent: float,
             features: Dict[str, float], qtype: str) -> dict:
    """Build the human-readable diagnosis block."""
    status, _ = classify_risk(risk_percent)
    if primary is None:
        if status == "HEALTHY":
            return {"root_cause": "All monitored parameters are inside their safe operating envelopes.",
                    "severity": "LOW",
                    "recommended_action": "Continue normal operation and keep the standard inspection schedule."}
        return {"root_cause": "The combined sensor pattern resembles past failures although no single "
                             "physical threshold is breached.",
                "severity": "MEDIUM" if status == "WARNING" else "HIGH",
                "recommended_action": "Schedule an inspection at the next shift and watch the trend closely."}
    cause = _cause_for(primary, features, qtype)
    extras = [MODE_NAMES[m] for m in modes if m != primary]
    if extras:
        cause += " Also flagged: " + ", ".join(extras) + "."
    return {"root_cause": cause,
            "severity": "HIGH" if status == "CRITICAL" else "MEDIUM",
            "recommended_action": MODE_ACTIONS[primary]
            + (" Halt the machine until cleared." if status == "CRITICAL" else "")}
