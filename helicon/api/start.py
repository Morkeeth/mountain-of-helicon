"""The start card as a surface: one page and one line.

  GET /api/start  : the card in plain words, plus the one line the menu bar shows.
  GET /start      : the same card as a page. The Mac app and a browser show this
                    same page, so the dashboard exists once.

A page load must not write a row, so this never records a reading; `helicon start`
in a terminal does that. Building the card asks git and the system about many
things, so it runs off the event loop and the result is kept for a minute: a menu
bar that asks every few seconds must not start a review each time.
"""
import asyncio
import os
import time

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
page_router = APIRouter()

_KEEP_SECONDS = 60
_kept = {"at": 0.0, "card": None}


def _build():
    from helicon.start import build_card, load_history, trend

    card = build_card(os.environ.get("HELICON_START_PATH") or os.path.join(os.path.expanduser("~"), ".claude"))
    history = load_history()
    card["history"], card["days"] = history, len(history)
    card["trend"] = {key: trend(history, key) for key in
                     ("instructions_broken", "memory_rotten", "rulings", "skills_never_opened", "sessions")}
    return card


async def _card():
    if _kept["card"] is None or time.time() - _kept["at"] > _KEEP_SECONDS:
        _kept["card"] = await asyncio.to_thread(_build)
        _kept["at"] = time.time()
    return _kept["card"]


@router.get("/start")
async def start_card():
    from helicon.start import menu_line, plain

    card = await _card()
    view = plain(card)
    line, to_fix = menu_line(card)
    return {
        "line": line, "to_fix": to_fix, "status": view["status"][0],
        "rows": view["rows"], "work": view.get("work", []), "system": view.get("system", []),
        "steps": [text for text, _ in view["steps"]], "read_seconds_ago": round(time.time() - _kept["at"]),
    }


@page_router.get("/start", response_class=HTMLResponse)
async def start_page():
    from helicon.start_html import render

    return HTMLResponse(render(await _card()), headers={"Cache-Control": "no-store"})
