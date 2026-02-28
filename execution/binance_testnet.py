from typing import Dict, Any


class BinanceTestnetExecutor:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
        order_size_usdt: float,
        public_api_url: str | None = None,
        private_api_url: str | None = None,
    ):
        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET are required for binance_testnet mode.")

        try:
            import ccxt  # type: ignore
        except ImportError as exc:
            raise RuntimeError("ccxt is required for Binance testnet execution. Install with: pip install ccxt") from exc

        self.symbol = symbol
        self.order_size_usdt = order_size_usdt
        self.exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        self.exchange.set_sandbox_mode(True)

        if isinstance(self.exchange.urls.get("api"), dict):
            if public_api_url:
                self.exchange.urls["api"]["public"] = public_api_url
            if private_api_url:
                self.exchange.urls["api"]["private"] = private_api_url

        try:
            self.exchange.load_markets()
        except Exception as exc:
            message = str(exc)
            lower_message = message.lower()
            if "451" in message or "restricted location" in lower_message:
                raise RuntimeError(
                    "Binance testnet is unavailable from this location (HTTP 451 restricted location). "
                    "Use paper mode or run from a supported region."
                ) from exc
            raise RuntimeError(
                "Failed to initialize Binance testnet connection. "
                "Check API keys, connectivity, and Binance testnet status."
            ) from exc

    def get_account_snapshot(self, mark_price: float | None = None) -> Dict[str, Any]:
        try:
            balance = self.exchange.fetch_balance()
        except Exception as exc:
            raise RuntimeError(f"Binance snapshot failed: {exc}") from exc
        base, quote = self.symbol.split("/")
        quote_free = float(balance.get(quote, {}).get("free", 0.0))
        base_free = float(balance.get(base, {}).get("free", 0.0))
        if mark_price is None:
            try:
                ticker = self.exchange.fetch_ticker(self.symbol)
            except Exception as exc:
                raise RuntimeError(f"Binance ticker fetch failed: {exc}") from exc
            mark_price = ticker.get("last")
        mark_price = float(mark_price or 0.0)
        equity = quote_free + (base_free * mark_price)
        return {
            "cash_usdt": quote_free,
            "asset_qty": base_free,
            "equity_usdt": equity,
        }

    def execute_signal(
        self,
        signal: Dict[str, Any],
        order_size_usdt: float | None = None,
        close_position: bool = False,
    ) -> Dict[str, Any]:
        signal_type = signal["type"].upper()
        side = "buy" if signal_type == "LONG" else "sell"
        size = self.order_size_usdt if order_size_usdt is None else float(order_size_usdt)

        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
        except Exception as exc:
            raise RuntimeError(f"Binance ticker fetch failed: {exc}") from exc
        price = ticker.get("last") or float(signal["price"])
        if not price:
            raise RuntimeError(f"Unable to determine price for {self.symbol}.")

        if side == "sell" and close_position:
            try:
                balance = self.exchange.fetch_balance()
            except Exception as exc:
                raise RuntimeError(f"Binance balance fetch failed: {exc}") from exc
            base, _ = self.symbol.split("/")
            raw_qty = float(balance.get(base, {}).get("free", 0.0))
            if raw_qty <= 0:
                return {
                    "executed": False,
                    "side": side.upper(),
                    "qty": 0.0,
                    "notional_usdt": 0.0,
                    "price": float(price),
                    "realized_pnl": None,
                    "message": f"Binance testnet SELL skipped | no free {base} balance.",
                }
        else:
            raw_qty = size / float(price)

        qty = float(self.exchange.amount_to_precision(self.symbol, raw_qty))
        if qty <= 0:
            raise ValueError(
                f"Computed quantity is 0 for {self.symbol}. Increase BINANCE_ORDER_SIZE_USDT."
            )

        try:
            order = self.exchange.create_market_order(self.symbol, side, qty)
        except Exception as exc:
            raise RuntimeError(f"Binance order placement failed: {exc}") from exc
        order_id = order.get("id", "unknown")
        notional = float(qty) * float(price)
        return {
            "executed": True,
            "side": side.upper(),
            "qty": qty,
            "notional_usdt": notional,
            "price": float(price),
            "realized_pnl": None,
            "message": (
                f"Binance testnet {side.upper()} submitted | "
                f"symbol={self.symbol}, qty={qty}, order_id={order_id}"
            ),
        }
