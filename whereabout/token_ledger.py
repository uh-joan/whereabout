"""Claude token budget circuit breaker. JSON file is authoritative for v1.0."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path

LEDGER_PATH = Path.home() / ".cache" / "whereabout" / "token-ledger.json"
DAILY_CAP = 50_000
PER_CALL_INPUT_CAP = 10_000
PER_CALL_OUTPUT_CAP = 2_000


class BudgetExceeded(Exception):
    pass


def check_and_record(input_tokens: int, output_tokens: int) -> None:
    """Raise BudgetExceeded if caps exceeded; otherwise record usage."""
    if input_tokens > PER_CALL_INPUT_CAP or output_tokens > PER_CALL_OUTPUT_CAP:
        raise BudgetExceeded(
            f"Per-call cap exceeded: input={input_tokens} (cap {PER_CALL_INPUT_CAP}), "
            f"output={output_tokens} (cap {PER_CALL_OUTPUT_CAP})"
        )
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ledger = _load()
    day_entry = ledger.get(today, {"input_tokens": 0, "output_tokens": 0})
    new_input = day_entry["input_tokens"] + input_tokens
    new_output = day_entry["output_tokens"] + output_tokens
    if new_input + new_output > DAILY_CAP:
        raise BudgetExceeded(f"Daily token cap ({DAILY_CAP}) exceeded")
    day_entry["input_tokens"] = new_input
    day_entry["output_tokens"] = new_output
    ledger[today] = day_entry
    _save(ledger)


def get_today_usage() -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _load().get(today, {"input_tokens": 0, "output_tokens": 0})


def _load() -> dict:
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text())
    return {}


def _save(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write via temp file + rename
    tmp = LEDGER_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=2))
    tmp.replace(LEDGER_PATH)
