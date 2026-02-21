from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backtesting.engine import run_backtest
from config import settings
from utils.runtime_state import RuntimeStateStore

DASHBOARD_DIR = BASE_DIR / "dashboard"
STATE_STORE = RuntimeStateStore(settings.STATE_DIR)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _symbols() -> list[str]:
    symbols = list(dict.fromkeys(settings.SYMBOLS))
    return symbols if symbols else [settings.SYMBOL]


def _payload() -> dict:
    runtime = STATE_STORE.load()
    symbols = _symbols()
    selected = runtime.get("selected_symbol") or settings.ACTIVE_SYMBOL or symbols[0]
    if selected not in symbols:
        selected = symbols[0]
        runtime["selected_symbol"] = selected
        STATE_STORE.save(runtime)

    paper_state = _read_json(BASE_DIR / settings.STATE_DIR / "paper_state.json")
    return {
        "mode": settings.BOT_MODE,
        "symbols": symbols,
        "selected_symbol": selected,
        "runtime": runtime,
        "scanner": runtime.get("scanner", {}),
        "risk": runtime.get("risk", {}),
        "paper_state": paper_state,
        "last_error": runtime.get("last_error"),
        "backtest": runtime.get("backtest"),
        "risk_config": {
            "MAX_DAILY_LOSS_PCT": settings.MAX_DAILY_LOSS_PCT,
            "MAX_TRADE_RISK_PCT": settings.MAX_TRADE_RISK_PCT,
            "MAX_TRADES_PER_DAY": settings.MAX_TRADES_PER_DAY,
            "MAX_CONSECUTIVE_LOSSES": settings.MAX_CONSECUTIVE_LOSSES,
        },
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def _send_json(self, data: dict, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._send_json(_payload())
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_body_json()

        if parsed.path == "/api/select-symbol":
            symbol = (body.get("symbol") or "").strip()
            symbols = _symbols()
            if symbol not in symbols:
                self._send_json({"ok": False, "error": "Invalid symbol selection."}, status=400)
                return
            runtime = STATE_STORE.load()
            runtime["selected_symbol"] = symbol
            STATE_STORE.save(runtime)
            self._send_json({"ok": True, "selected_symbol": symbol})
            return

        if parsed.path == "/api/backtest":
            payload = _payload()
            symbol = (body.get("symbol") or "").strip() or payload["selected_symbol"]
            period = (body.get("period") or "").strip() or settings.PERIOD
            timeframe = (body.get("timeframe") or "").strip() or settings.TIMEFRAME
            result = run_backtest(symbol=symbol, period=period, timeframe=timeframe)
            runtime = STATE_STORE.load()
            runtime["backtest"] = result
            STATE_STORE.save(runtime)
            self._send_json({"ok": True, "result": result})
            return

        self._send_json({"ok": False, "error": "Not found."}, status=404)


def run() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 5001), DashboardHandler)
    print("Dashboard running on http://localhost:5001")
    server.serve_forever()


if __name__ == "__main__":
    run()
