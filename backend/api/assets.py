"""Fleet asset registry, connection handshake and health summary."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.database import get_db
from backend.models import Asset
from backend.schemas import (AssetCreate, AssetOut, ConnectRequest, ConnectResponse, HealthSummary)

router = APIRouter(prefix="/api/assets", tags=["assets"], dependencies=[Depends(get_current_user)])
HANDSHAKE_MIN_MS, HANDSHAKE_MAX_MS = 18.0, 64.0   # simulated link-up latency window


@router.get("", response_model=List[AssetOut])
async def list_assets(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Asset).order_by(Asset.id))).scalars().all()


@router.post("", response_model=AssetOut, status_code=201)
async def create_asset(body: AssetCreate, db: AsyncSession = Depends(get_db)):
    next_id = (await db.execute(select(func.coalesce(func.max(Asset.id), 0)))).scalar_one() + 1
    asset = Asset(tag=f"UNIT_{next_id:02d}", name=body.name, asset_type=body.asset_type,
                  ip_address=body.ip_address, protocol=body.protocol)
    db.add(asset)
    await db.commit()
    return asset


@router.get("/summary/health", response_model=HealthSummary)
async def health_summary(db: AsyncSession = Depends(get_db)):
    assets = (await db.execute(select(Asset))).scalars().all()
    counts = {"HEALTHY": 0, "WARNING": 0, "CRITICAL": 0}
    for a in assets:
        counts[a.status] = counts.get(a.status, 0) + 1
    avg = sum(a.last_risk_percent for a in assets) / len(assets) if assets else 0.0
    return HealthSummary(
        total_assets=len(assets), connected_assets=sum(a.connected for a in assets),
        healthy=counts["HEALTHY"], warning=counts["WARNING"], critical=counts["CRITICAL"],
        average_risk_percent=round(avg, 1), fleet_health_score=round(100.0 - avg, 1))


@router.post("/{asset_id}/connect", response_model=ConnectResponse)
async def connect_asset(asset_id: int, body: ConnectRequest, db: AsyncSession = Depends(get_db)):
    """Registers the endpoint and marks the asset connected.

    The handshake is simulated. To talk to real hardware, replace the marked block
    with an asyncua (OPC-UA) or paho-mqtt client call (see README, "Real hardware").
    """
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Machine not found.")
    # --- simulated handshake (replace with a real protocol client) ---
    handshake_ms = round(random.uniform(HANDSHAKE_MIN_MS, HANDSHAKE_MAX_MS), 1)
    # -----------------------------------------------------------------
    asset.ip_address, asset.protocol, asset.connected = body.ip_address, body.protocol, True
    asset.last_seen = datetime.now(timezone.utc)
    await db.commit()
    return ConnectResponse(asset=AssetOut.model_validate(asset), handshake_ms=handshake_ms, simulated=True,
                           message=f"{asset.name} linked over {body.protocol} at {body.ip_address}.")
