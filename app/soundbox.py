"""The "Soundbox": Bulbul TTS played on the laptop speaker (stands in for the counter speaker).

One speaker, one queue: announcements play strictly one after another. (Two merchants share this
laptop in the demo, so their clips would otherwise talk over each other.)
"""
import logging
import queue
import subprocess
import threading
import time

from app import sarvam
from app.config import ROOT

log = logging.getLogger("soundbox")
DIR = ROOT / "var" / "soundbox"
GAP_SECONDS = 0.8

_queue: queue.Queue[tuple[str, str]] = queue.Queue()
_worker: threading.Thread | None = None
_lock = threading.Lock()


def announce(text: str, language_code: str) -> None:
    """Non-blocking: queue the announcement; the WhatsApp reply doesn't wait for audio."""
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_drain, daemon=True, name="soundbox")
            _worker.start()
    _queue.put((text, language_code))


def _drain() -> None:
    while True:
        text, language_code = _queue.get()
        try:
            _play(text, language_code)
        finally:
            _queue.task_done()
        time.sleep(GAP_SECONDS)


def _play(text: str, language_code: str) -> None:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        path = DIR / f"{int(time.time() * 1000)}.wav"
        path.write_bytes(sarvam.speak(text, language_code))
        log.info("🔊 Soundbox: %s", text)
        subprocess.run(["afplay", str(path)], check=False)
    except Exception as e:
        log.warning("Soundbox failed (%s): %s", e, text)
