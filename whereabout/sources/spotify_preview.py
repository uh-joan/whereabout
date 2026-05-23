"""Audio preview via Deezer's public API — no auth required."""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path

import httpx

_current_proc: subprocess.Popen | None = None
_current_tmp: Path | None = None


def get_preview_info(artist: str, *_args, **_kwargs) -> dict | None:
    """Return {url, title, artist} for the top Deezer match, or None."""
    resp = httpx.get(
        "https://api.deezer.com/search/track",
        params={"q": artist, "limit": 1},
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json().get("data", [])
    if not items:
        return None
    track = items[0]
    url = track.get("preview")
    if not url:
        return None
    return {
        "url": url,
        "title": track.get("title", ""),
        "artist": track.get("artist", {}).get("name", artist),
    }


def get_preview_url(artist: str, *_args, **_kwargs) -> str | None:
    info = get_preview_info(artist)
    return info["url"] if info else None


def play_preview(preview_url: str) -> subprocess.Popen | None:
    global _current_proc, _current_tmp
    stop_preview()
    audio = httpx.get(preview_url, timeout=15).content
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.write(audio)
    tmp.flush()
    tmp.close()
    _current_tmp = Path(tmp.name)
    _current_proc = subprocess.Popen(
        ["afplay", str(_current_tmp)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return _current_proc


def stop_preview() -> None:
    global _current_proc, _current_tmp
    if _current_proc and _current_proc.poll() is None:
        _current_proc.terminate()
        try:
            _current_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _current_proc.kill()
    _current_proc = None
    if _current_tmp and _current_tmp.exists():
        try:
            _current_tmp.unlink()
        except OSError:
            pass
    _current_tmp = None
