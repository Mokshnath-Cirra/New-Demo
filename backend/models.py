"""SQLAlchemy 2.0 ORM models: users, assets, telemetry_logs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(20), default="operator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag: Mapped[str] = mapped_column(String(24), unique=True)           # e.g. EQ-1001
    name: Mapped[str] = mapped_column(String(80))
    asset_type: Mapped[str] = mapped_column(String(40))
    ip_address: Mapped[str] = mapped_column(String(45))
    protocol: Mapped[str] = mapped_column(String(16), default="OPC-UA")
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(12), default="HEALTHY")
    last_risk_percent: Mapped[float] = mapped_column(Float, default=0.0)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    logs: Mapped[List["TelemetryLog"]] = relationship(back_populates="asset")


class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.id"), index=True, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    quality_type: Mapped[str] = mapped_column(String(1))
    air_temperature: Mapped[float] = mapped_column(Float)
    process_temperature: Mapped[float] = mapped_column(Float)
    rotational_speed: Mapped[float] = mapped_column(Float)
    torque: Mapped[float] = mapped_column(Float)
    tool_wear: Mapped[float] = mapped_column(Float)
    risk_percent: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), index=True)
    failure_mode: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    rul_hours: Mapped[float] = mapped_column(Float, default=0.0)
    efficiency_percent: Mapped[float] = mapped_column(Float, default=0.0)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset: Mapped[Optional[Asset]] = relationship(back_populates="logs")
