# AURA AI - Enterprise Fleet & Machinery Health Suite

Predicts machine failure from sensor telemetry, explains the cause, and tracks fleet health and savings.

**Stack:** FastAPI + async SQLAlchemy 2.0 (SQLite or PostgreSQL) - scikit-learn Random Forests - vanilla JS SPA (Chart.js) - NGINX - Docker Compose.

```
AURA-AI/
 ml/          feature_engineering.py (DeltaT, power W, overstrain index), train.py, artifacts/
 backend/     main.py, config.py, database.py, models.py, schemas.py, api/, services/
 frontend/    index.html, css/, js/, nginx.conf, Dockerfile.frontend
 tests/       test_core.py
 run.py       one-command launcher        docker-compose.yml   production stack
```

**Live website:** see {https://aura-ai-whm9.onrender.com} (GitHub + Render, free tier, auto-deploys on every push).

## 1. Local development

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# optional but recommended: put the real dataset at data/ai4i2020.csv (see data/README.txt)
python run.py                                          # trains on first run, opens http://127.0.0.1:8000
```
Or run manually: `python -m ml.train` then `uvicorn backend.main:app --reload`. API docs: `/docs`. Tests: `pytest -q`.
Local mode uses SQLite (`data/aura.db`) and anonymous access. Set `REQUIRE_AUTH=true` to require sign-in
(admin user comes from `DEMO_ADMIN_USER` / `DEMO_ADMIN_PASSWORD`).

## 2. Docker (PostgreSQL + FastAPI + NGINX)

```bash
cp .env.example .env        # set SECRET_KEY, POSTGRES_PASSWORD, DEMO_ADMIN_PASSWORD, CORS_ORIGINS
docker compose up -d --build
docker compose logs -f backend      # first start trains the model if artifacts are missing
```
Open `http://127.0.0.1:8080` (change `FRONTEND_BIND=0.0.0.0:80` to expose directly). Data persists in the `pgdata` volume.
Update later with `git pull && docker compose up -d --build`. Backup: `docker compose exec postgres_db pg_dump -U aura aura_ai > backup.sql`.

## 3. Cloud VPS (DigitalOcean, AWS EC2, any Ubuntu server)

1. Create an Ubuntu 22.04+ server (2 GB RAM minimum). Open ports 22, 80, 443 only (firewall / security group).
2. Point your domain's **A record** (e.g. `aura.example.com`) at the server IP.
3. Install Docker and the host NGINX + Certbot:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx git
   ```
4. Clone the project, then `cp .env.example .env` and fill in strong secrets. Set `ENVIRONMENT=production`,
   `CORS_ORIGINS=https://aura.example.com`, keep `FRONTEND_BIND=127.0.0.1:8080`. Start: `docker compose up -d --build`.
5. Create `/etc/nginx/sites-available/aura`:
   ```nginx
   server {
     listen 80;
     server_name aura.example.com;
     location / {
       proxy_pass http://127.0.0.1:8080;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
     }
   }
   ```
   ```bash
   sudo ln -s /etc/nginx/sites-available/aura /etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx
   ```
6. Issue the SSL certificate (auto-renews): `sudo certbot --nginx -d aura.example.com`. Verify `https://aura.example.com/api/health`.

**Render / Railway:** create a managed PostgreSQL, deploy the repo as a Docker service using `backend/Dockerfile.backend`
(set `DATABASE_URL=postgresql+asyncpg://...`, `SECRET_KEY`, `REQUIRE_AUTH=true`, `PORT` if required), and host `frontend/` as a static
site or a second Docker service with `frontend/Dockerfile.frontend`. Point the frontend's `/api` calls at the backend by
setting `window.AURA_API_BASE` in `index.html` and adding the frontend URL to `CORS_ORIGINS`.

## API summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/predict` | Single prediction + diagnosis (rate-limited 60/min per IP) |
| GET | `/api/assets` - POST `/api/assets` | List / register machines |
| POST | `/api/assets/{id}/connect` | Link a machine (IP + protocol) |
| GET | `/api/assets/summary/health` | Fleet health counts |
| GET | `/api/telemetry/history` | Audit log of evaluations |
| GET | `/api/metrics/roi` - `/api/model/metrics` | Savings model - model KPIs |
| POST | `/api/auth/login` - `/signup` - GET `/me` | JWT auth |
| GET | `/api/health` | Liveness + model status |

## Important notes

- **Real hardware:** the "Connect Machine" handshake and the live telemetry chart are **simulated**. To read real sensors,
  replace the marked block in `backend/api/assets.py` with an `asyncua` (OPC-UA) or `paho-mqtt` client and feed readings to `/api/predict`.
- **Risk floor:** if a deterministic physics rule is breached (heat dissipation, power band, overstrain), the reported risk is never below a
  fixed floor (`PHYSICS_RISK_FLOOR` in `ml_service.py`). If the model cannot load, the system falls back to the rules alone.
- **RUL and efficiency** are heuristic estimates derived from risk and tool wear (see `diagnostics.py`), not separately trained models.
- **ROI** figures are driven by the editable assumptions in `.env` and count each high-risk evaluation as one prevented failure.
- Production checklist: strong `SECRET_KEY`, `REQUIRE_AUTH=true`, restricted `CORS_ORIGINS`, change the admin password, HTTPS only, regular DB backups.
