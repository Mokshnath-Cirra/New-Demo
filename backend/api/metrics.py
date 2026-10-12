"""Model KPIs and ROI / cost-savings analytics."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.config import settings
from backend.database import get_db
from backend.models import Asset, TelemetryLog
from backend.schemas import RoiSummary

router = APIRouter(prefix="/api", tags=["metrics"], dependencies=[Depends(get_current_user)])
ROI_WINDOW_DAYS = 30


@router.get("/model/metrics")
async def model_metrics() -> Dict:
    path = settings.ARTIFACT_DIR / "metrics.json"
    if not path.exists():
        raise HTTPException(503, "Model metrics are not available. Run `python -m ml.train`.")
    return json.loads(path.read_text())


@router.get("/metrics/roi", response_model=RoiSummary)
async def roi(db: AsyncSession = Depends(get_db)):
    """Savings model: every CRITICAL evaluation is treated as one failure prevented by an
    early planned intervention. All inputs are editable business assumptions."""
    since = datetime.now(timezone.utc) - timedelta(days=ROI_WINDOW_DAYS)
    in_window = TelemetryLog.timestamp >= since
    total = (await db.execute(select(func.count(TelemetryLog.id)).where(in_window))).scalar_one()
    critical = (await db.execute(select(func.count(TelemetryLog.id)).where(
        in_window, TelemetryLog.status == "CRITICAL"))).scalar_one()
    machines = max(1, (await db.execute(select(func.count(Asset.id)))).scalar_one())
    gain = hours_gain = critical * settings.AVG_DOWNTIME_HOURS_PER_FAILURE
    gain = round(hours_gain / (machines * settings.SCHEDULED_HOURS_PER_MONTH) * 100, 1)
    loss_per_failure = settings.AVG_DOWNTIME_HOURS_PER_FAILURE * settings.DOWNTIME_COST_PER_HOUR_USD
    hours = critical * settings.AVG_DOWNTIME_HOURS_PER_FAILURE
    downtime_saved = hours * settings.DOWNTIME_COST_PER_HOUR_USD
    repair_saved = critical * (settings.UNPLANNED_REPAIR_COST_USD - settings.PLANNED_REPAIR_COST_USD)
    return RoiSummary(
        evaluations=total, prevented_failures=critical,
        avg_downtime_loss_per_failure_usd=loss_per_failure, downtime_hours_avoided=hours,
        downtime_cost_saved_usd=downtime_saved, repair_cost_saved_usd=repair_saved,
        total_savings_usd=downtime_saved + repair_saved, efficiency_gain_percent=gain,
        assumptions={"downtime_cost_per_hour_usd": settings.DOWNTIME_COST_PER_HOUR_USD,
                     "avg_downtime_hours_per_failure": settings.AVG_DOWNTIME_HOURS_PER_FAILURE,
                     "unplanned_repair_cost_usd": settings.UNPLANNED_REPAIR_COST_USD,
                     "planned_repair_cost_usd": settings.PLANNED_REPAIR_COST_USD,
                     "scheduled_hours_per_month": settings.SCHEDULED_HOURS_PER_MONTH})
