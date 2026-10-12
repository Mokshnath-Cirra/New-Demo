"""Pydantic v2 request/response schemas."""
from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC so clients parse correctly."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]
Protocol = Literal["OPC-UA", "MQTT"]


class PredictRequest(BaseModel):
    type: Literal["L", "M", "H"] = "M"
    air_temperature: float = Field(ge=290, le=310, description="Kelvin")
    process_temperature: float = Field(ge=300, le=320, description="Kelvin")
    rotational_speed: float = Field(ge=1000, le=3000, description="RPM")
    torque: float = Field(ge=1, le=100, description="Nm")
    tool_wear: float = Field(ge=0, le=300, description="minutes")
    asset_id: Optional[int] = None
    persist: bool = True


class StressFactor(BaseModel):
    key: str
    label: str
    value: float  # 0-100


class Diagnosis(BaseModel):
    root_cause: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    recommended_action: str


class PredictResponse(BaseModel):
    status_code: Literal["HEALTHY", "WARNING", "CRITICAL"]
    status_label: str
    is_failure: bool
    risk_percent: float
    efficiency_percent: float
    rul_hours: float
    primary_failure_mode: Optional[str]
    failure_modes: List[str]
    physics: dict
    stress_factors: List[StressFactor]
    diagnosis: Diagnosis
    engine: Literal["ml", "physics-fallback"]
    latency_ms: float
    log_id: Optional[int] = None
    asset_id: Optional[int] = None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tag: str
    name: str
    asset_type: str
    ip_address: str
    protocol: str
    connected: bool
    status: str
    last_risk_percent: float
    last_seen: Optional[UTCDateTime]


class AssetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    asset_type: str = Field(min_length=2, max_length=40)
    ip_address: str
    protocol: Protocol = "OPC-UA"

    @field_validator("ip_address")
    @classmethod
    def _valid_ip(cls, v: str) -> str:
        ipaddress.ip_address(v)  # raises ValueError -> 422
        return v


class ConnectRequest(BaseModel):
    ip_address: str
    protocol: Protocol

    @field_validator("ip_address")
    @classmethod
    def _valid_ip(cls, v: str) -> str:
        ipaddress.ip_address(v)
        return v


class ConnectResponse(BaseModel):
    asset: AssetOut
    handshake_ms: float
    simulated: bool
    message: str


class HealthSummary(BaseModel):
    total_assets: int
    connected_assets: int
    healthy: int
    warning: int
    critical: int
    average_risk_percent: float
    fleet_health_score: float


class HistoryItem(BaseModel):
    id: int
    timestamp: UTCDateTime
    asset_id: Optional[int]
    equipment_tag: str
    equipment_name: str
    risk_percent: float
    status: str
    failure_mode: Optional[str]
    rul_hours: float


class RoiSummary(BaseModel):
    evaluations: int
    prevented_failures: int
    avg_downtime_loss_per_failure_usd: float
    downtime_hours_avoided: float
    downtime_cost_saved_usd: float
    repair_cost_saved_usd: float
    total_savings_usd: float
    efficiency_gain_percent: float
    assumptions: dict


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
