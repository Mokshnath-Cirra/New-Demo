# Single-service image (API + UI) used by Render, Railway and Fly.io.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY ml ./ml
COPY data ./data
COPY frontend ./frontend
# Train at build time (uses data/ai4i2020.csv when present, synthetic data otherwise).
RUN python -m ml.train
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
