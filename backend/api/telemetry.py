"""Prediction endpoint and evaluation history."""
from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.api.auth import get_current_user
from backend.database import get_db
from backend.models import Asset, TelemetryLog, User
from backend.schemas import HistoryItem, PredictRequest, PredictResponse

router = APIRouter(prefix="/api", tags=["telemetry"])
MAX_HISTORY = 200


async def store_evaluation(db: AsyncSession, req: PredictRequest, result: dict,
                           user: Optional[User], when: Optional[datetime] = None) -> TelemetryLog:
    """Persist one evaluation and refresh the owning asset's live status."""
    log = TelemetryLog(
        asset_id=req.asset_id, user_id=user.id if user else None,
        timestamp=when or datetime.now(timezone.utc), quality_type=req.type,
        air_temperature=req.air_temperature, process_temperature=req.process_temperature,
        rotational_speed=req.rotational_speed, torque=req.torque, tool_wear=req.tool_wear,
        risk_percent=result["risk_percent"], status=result["status_code"],
        failure_mode=result["primary_failure_mode"], rul_hours=result["rul_hours"],
        efficiency_percent=result["efficiency_percent"],
        diagnosis=result["diagnosis"]["root_cause"])
    db.add(log)
    if req.asset_id is not None:
        asset = await db.get(Asset, req.asset_id)
        if asset is not None:
            asset.status, asset.last_risk_percent = result["status_code"], result["risk_percent"]
            asset.last_seen = log.timestamp
    await db.commit()
    return log


@router.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest, request: Request, db: AsyncSession = Depends(get_db),
                  user: Optional[User] = Depends(get_current_user)):
    if req.asset_id is not None and await db.get(Asset, req.asset_id) is None:
        raise HTTPException(404, "Machine not found.")
    started = perf_counter()
    result = await run_in_threadpool(request.app.state.ml.predict, req.model_dump())
    result["latency_ms"] = round((perf_counter() - started) * 1000, 1)
    log = await store_evaluation(db, req, result, user) if req.persist else None
    return PredictResponse(**result, log_id=log.id if log else None, asset_id=req.asset_id)


@router.get("/telemetry/history", response_model=List[HistoryItem],
            dependencies=[Depends(get_current_user)])
async def history(limit: int = Query(50, ge=1, le=MAX_HISTORY), asset_id: Optional[int] = None,
                  db: AsyncSession = Depends(get_db)):
    stmt = (select(TelemetryLog, Asset).join(Asset, TelemetryLog.asset_id == Asset.id, isouter=True)
            .order_by(TelemetryLog.timestamp.desc()).limit(limit))
    if asset_id is not None:
        stmt = stmt.where(TelemetryLog.asset_id == asset_id)
    rows = (await db.execute(stmt)).all()
    return [HistoryItem(
        id=log.id, timestamp=log.timestamp, asset_id=log.asset_id,
        equipment_tag=asset.tag if asset else "MANUAL", equipment_name=asset.name if asset else "Unassigned test",
        risk_percent=log.risk_percent, status=log.status, failure_mode=log.failure_mode,
        rul_hours=log.rul_hours) for log, asset in rows]
