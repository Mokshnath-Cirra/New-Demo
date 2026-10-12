"""AURA AI - single-command launcher:  python run.py"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from backend.config import settings  # noqa: E402

BROWSER_DELAY_S = 1.5


def ensure_models() -> None:
    """Train automatically on first run so a fresh clone works out of the box."""
    if (settings.ARTIFACT_DIR / "model_binary.joblib").exists():
        print("[AURA] ML artifacts found.")
        return
    print("[AURA] No trained model found - training now (about 10 seconds)...")
    from ml.train import run_training_pipeline
    metrics = run_training_pipeline()
    print(f"[AURA] Trained on {metrics['data_source']} data: accuracy {metrics['accuracy']:.1%}, "
          f"recall {metrics['recall']:.1%}")


def open_browser(url: str) -> None:
    time.sleep(BROWSER_DELAY_S)
    try:
        webbrowser.open_new_tab(url)
    except webbrowser.Error as exc:
        print(f"[AURA] Could not open the browser automatically: {exc}")


def main() -> None:
    import uvicorn
    ensure_models()
    url = f"http://{settings.HOST}:{settings.PORT}"
    print(f"[AURA] Dashboard: {url}   API docs: {url}/docs")
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)


if __name__ == "__main__":
    main()
