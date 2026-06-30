"""
MSE Sentiment — Run State Manager
Tracks last run times for each scraper.
On restart, only runs scrapers that are due based on their interval.
"""

import os
import json
from datetime import datetime, timezone

STATE_FILE = ".scraper_state.json"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_due(scraper_name: str, interval_minutes: int) -> bool:
    """Check if a scraper is due to run based on last run time."""
    state = load_state()
    last_run = state.get(scraper_name)

    if not last_run:
        return True  # never run before

    last_run_dt = datetime.fromisoformat(last_run)
    now         = datetime.now(timezone.utc)
    elapsed     = (now - last_run_dt).total_seconds() / 60

    if elapsed >= interval_minutes:
        print(f"  [{scraper_name}] Due — last run {elapsed:.0f} min ago")
        return True
    else:
        print(f"  [{scraper_name}] Skipping — ran {elapsed:.0f} min ago (interval: {interval_minutes} min)")
        return False


def mark_done(scraper_name: str):
    """Mark a scraper as just completed."""
    state = load_state()
    state[scraper_name] = datetime.now(timezone.utc).isoformat()
    save_state(state)


def is_first_run() -> bool:
    state = load_state()
    return not state.get("first_run_done", False)


def mark_first_run_done():
    state = load_state()
    state["first_run_done"] = True
    state["first_run_at"]   = datetime.now(timezone.utc).isoformat()
    save_state(state)
