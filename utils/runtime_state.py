import json
import os
from datetime import datetime, timezone
from typing import Any, Dict


class RuntimeStateStore:
    def __init__(self, state_dir: str):
        self.state_dir = state_dir
        self.state_file = os.path.join(state_dir, "runtime_state.json")
        os.makedirs(self.state_dir, exist_ok=True)

    def _default_state(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "last_signal_key": None,
            "selected_symbol": None,
            "scanner": {},
            "learning": {},
            "cycles": 0,
            "signals_detected": 0,
            "executions_attempted": 0,
            "errors": 0,
            "started_at_utc": now,
            "updated_at_utc": now,
            "last_cycle_at_utc": None,
            "last_error": None,
        }

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_file):
            return self._default_state()

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            return self._default_state()

        defaults = self._default_state()
        defaults.update(state)
        return defaults

    def save(self, state: Dict[str, Any]) -> None:
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
