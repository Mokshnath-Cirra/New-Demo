"""First-run seed: demo fleet, a few historical evaluations and the admin user."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import hash_password
from backend.api.telemetry import store_evaluation
from backend.config import settings
from backend.models import Asset, User
from backend.schemas import PredictRequest
from backend.services.ml_service import MLService

FLEET = [
    ("CNC_LATHE_01", "CNC Lathe Unit 01", "Turning center", "192.168.1.50", "OPC-UA"),
    ("MILLING_02", "Milling Machine 02", "Vertical mill", "192.168.1.51", "OPC-UA"),
    ("PRESS_03", "Hydraulic Press 03", "400 t press", "192.168.1.52", "MQTT"),
    ("ROBOT_ARM_04", "Robotic Arm 04", "6-axis welder", "192.168.1.53", "MQTT"),
]
# (asset index, hours ago, type, air K, process K, rpm, torque Nm, wear min)
SAMPLES = [
    (0, 70, "M", 300.1, 310.2, 1490, 41, 40), (0, 30, "M", 300.4, 310.5, 1510, 44, 95),
    (0, 3, "M", 300.2, 310.3, 1500, 40, 130),
    (1, 60, "L", 300.0, 310.1, 1480, 38, 60), (1, 20, "L", 303.0, 308.0, 1250, 62, 110),
    (1, 2, "L", 303.2, 308.1, 1260, 60, 118),
    (2, 48, "H", 299.8, 309.9, 1530, 36, 20), (2, 6, "H", 300.0, 310.0, 1510, 39, 45),
    (3, 40, "M", 300.3, 310.4, 2600, 75, 90), (3, 10, "M", 300.1, 310.1, 1550, 42, 210),
    (3, 1, "M", 300.0, 310.0, 1500, 40, 235),
]


async def seed_database(db: AsyncSession, ml: MLService) -> None:
    if not (await db.execute(select(func.count(User.id)))).scalar_one():
        db.add(User(username=settings.DEMO_ADMIN_USER, role="admin",
                    password_hash=hash_password(settings.DEMO_ADMIN_PASSWORD)))
    if (await db.execute(select(func.count(Asset.id)))).scalar_one():
        await db.commit()
        return
    now = datetime.now(timezone.utc)
    assets = [Asset(tag=t, name=n, asset_type=k, ip_address=ip, protocol=p, connected=False, last_seen=now)
              for t, n, k, ip, p in FLEET]
    db.add_all(assets)
    await db.flush()
    for idx, hours_ago, q, air, proc, rpm, torque, wear in SAMPLES:
        req = PredictRequest(type=q, air_temperature=air, process_temperature=proc,
                             rotational_speed=rpm, torque=torque, tool_wear=wear,
                             asset_id=assets[idx].id)
        await store_evaluation(db, req, ml.predict(req.model_dump()), None,
                               when=now - timedelta(hours=hours_ago))
