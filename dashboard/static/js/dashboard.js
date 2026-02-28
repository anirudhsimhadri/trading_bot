const state = {
  data: {},
  chart: null,
};

function num(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "-";
  return Number(v).toFixed(digits);
}

function populateSymbolSelector(symbols, selected) {
  const select = document.getElementById("symbol-select");
  select.innerHTML = "";
  symbols.forEach((sym) => {
    const option = document.createElement("option");
    option.value = sym;
    option.textContent = sym;
    if (sym === selected) option.selected = true;
    select.appendChild(option);
  });
}

function renderScanner(scanner, selectedSymbol) {
  const body = document.querySelector("#scanner-table tbody");
  body.innerHTML = "";
  const symbols = Object.keys(scanner || {}).sort();

  symbols.forEach((sym) => {
    const row = scanner[sym];
    const tr = document.createElement("tr");
    if (sym === selectedSymbol) tr.style.background = "rgba(22,195,160,0.12)";

    const signal = row.signal || "—";
    const model = row.strategy || "—";
    const regime = row.regime
      ? `${row.regime} (${num(row.regime_confidence, 2)})`
      : "—";
    const hasClose =
      row.last_close !== null &&
      row.last_close !== undefined &&
      !Number.isNaN(Number(row.last_close));
    const hasStale =
      row.stale_minutes !== null &&
      row.stale_minutes !== undefined &&
      !Number.isNaN(Number(row.stale_minutes));
    const signalColor = signal === "LONG" ? "positive" : signal === "SHORT" ? "negative" : "";
    tr.innerHTML = `
      <td>${sym}</td>
      <td>${model}</td>
      <td>${regime}</td>
      <td class="${signalColor}">${signal}</td>
      <td>${row.score ?? "—"}</td>
      <td>${hasClose ? num(row.last_close, 2) : "—"}</td>
      <td>${row.data_rows ?? 0}</td>
      <td>${hasStale ? num(row.stale_minutes, 1) : "—"}</td>
    `;
    body.appendChild(tr);
  });
}

function renderStats(payload) {
  document.getElementById("mode-pill").textContent = `Mode: ${payload.mode}`;
  document.getElementById("cycle-pill").textContent = `Cycles: ${payload.runtime?.cycles || 0}`;
  document.getElementById("selected-symbol").textContent = payload.selected_symbol || "-";
  document.getElementById("signals-detected").textContent = payload.runtime?.signals_detected || 0;
  document.getElementById("executions").textContent = payload.runtime?.executions_attempted || 0;
  document.getElementById("errors").textContent = payload.runtime?.errors || 0;

  const risk = payload.risk || {};
  const riskCfg = payload.risk_config || {};
  document.getElementById("risk-trades").textContent = risk.trades_today ?? 0;
  const pnlEl = document.getElementById("risk-pnl");
  const pnl = Number(risk.realized_pnl_today || 0);
  pnlEl.textContent = num(pnl, 2);
  pnlEl.classList.toggle("positive", pnl > 0);
  pnlEl.classList.toggle("negative", pnl < 0);
  document.getElementById("risk-losses").textContent = risk.consecutive_losses ?? 0;
  document.getElementById("risk-cooldown").textContent = risk.cooldown_until_utc || "None";
  document.getElementById("risk-daily-limit").innerHTML = `Daily Loss Limit: <strong>${num(riskCfg.MAX_DAILY_LOSS_PCT, 2)}%</strong>`;
  document.getElementById("risk-trade-risk").innerHTML = `Risk Per Trade: <strong>${num(riskCfg.MAX_TRADE_RISK_PCT, 2)}%</strong>`;

  const paper = payload.paper_state || {};
  document.getElementById("paper-cash").textContent = num(paper.cash_usdt, 2);
  document.getElementById("paper-asset").textContent = num(paper.asset_qty, 6);
  document.getElementById("paper-entry").textContent = num(paper.avg_entry_price, 2);
  document.getElementById("paper-realized").textContent = num(paper.realized_pnl_total, 2);

  populateSymbolSelector(payload.symbols || [], payload.selected_symbol);
  renderScanner(payload.scanner || {}, payload.selected_symbol);
}

function renderBacktest(backtest) {
  const metricWrap = document.getElementById("backtest-metrics");
  metricWrap.innerHTML = "";
  if (!backtest || backtest.error) {
    const div = document.createElement("div");
    div.className = "metric";
    div.innerHTML = `<p class="k">Backtest</p><p class="v">${backtest?.error || "Run a backtest to view metrics."}</p>`;
    metricWrap.appendChild(div);
    return;
  }

  const metrics = backtest.metrics || {};
  const metricMap = [
    ["Total Return %", num(metrics.total_return_pct, 2)],
    ["Net Profit", num(metrics.net_profit, 2)],
    ["Max Drawdown %", num(metrics.max_drawdown_pct, 2)],
    ["Sharpe", num(metrics.sharpe, 2)],
    ["Trades", metrics.trades ?? 0],
    ["Win Rate %", num(metrics.win_rate_pct, 2)],
    ["Profit Factor", num(metrics.profit_factor, 2)],
  ];
  if ((metrics.validation_mode || "") === "walk_forward") {
    metricMap.push(["WF Splits", metrics.splits ?? 0]);
    metricMap.push(["WF Pass %", num(metrics.split_pass_rate_pct, 2)]);
  }

  metricMap.forEach(([k, v]) => {
    const div = document.createElement("div");
    div.className = "metric";
    div.innerHTML = `<p class="k">${k}</p><p class="v">${v}</p>`;
    metricWrap.appendChild(div);
  });

  const labels = (backtest.equity_curve || []).map((p) => p.time);
  const values = (backtest.equity_curve || []).map((p) => p.equity);
  const ctx = document.getElementById("equity-chart");

  if (state.chart) state.chart.destroy();
  state.chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: `${backtest.symbol} Equity`,
          data: values,
          borderColor: "#16c3a0",
          backgroundColor: "rgba(22,195,160,0.15)",
          tension: 0.22,
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: "#d7eef4", font: { family: "Space Grotesk" } },
        },
      },
      scales: {
        x: { ticks: { color: "#8db4c0", maxTicksLimit: 8 }, grid: { color: "rgba(141,180,192,0.08)" } },
        y: { ticks: { color: "#8db4c0" }, grid: { color: "rgba(141,180,192,0.08)" } },
      },
    },
  });

  const tradesBody = document.querySelector("#trades-table tbody");
  tradesBody.innerHTML = "";
  (backtest.trades || []).slice(-60).reverse().forEach((t) => {
    const tr = document.createElement("tr");
    const pnlClass = Number(t.pnl) >= 0 ? "positive" : "negative";
    tr.innerHTML = `
      <td>${t.entry_time || "-"}</td>
      <td>${t.exit_time || "-"}</td>
      <td>${num(t.entry_price, 2)}</td>
      <td>${num(t.exit_price, 2)}</td>
      <td>${num(t.qty, 6)}</td>
      <td class="${pnlClass}">${num(t.pnl, 2)}</td>
      <td class="${pnlClass}">${num(t.return_pct, 2)}</td>
    `;
    tradesBody.appendChild(tr);
  });
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const payload = await res.json();
    state.data = payload;
    renderStats(payload);
    renderBacktest(payload.backtest);
  } catch (err) {
    console.error("Status refresh failed", err);
  }
}

async function setSelectedSymbol() {
  const symbol = document.getElementById("symbol-select").value;
  await fetch("/api/select-symbol", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol }),
  });
  await refreshStatus();
}

async function runBacktest() {
  const symbol = document.getElementById("symbol-select").value;
  const period = document.getElementById("backtest-period").value || "60d";
  const timeframe = document.getElementById("backtest-timeframe").value || "15m";
  const btn = document.getElementById("run-backtest-btn");
  btn.disabled = true;
  btn.textContent = "Running...";
  try {
    const res = await fetch("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, period, timeframe }),
    });
    const payload = await res.json();
    if (payload.ok) {
      renderBacktest(payload.result);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Backtest";
  }
}

async function runWalkForward() {
  const symbol = document.getElementById("symbol-select").value;
  const period = document.getElementById("backtest-period").value || "6mo";
  const timeframe = document.getElementById("backtest-timeframe").value || "15m";
  const btn = document.getElementById("run-wf-btn");
  btn.disabled = true;
  btn.textContent = "Running...";
  try {
    const res = await fetch("/api/walkforward", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, period, timeframe }),
    });
    const payload = await res.json();
    if (payload.ok) {
      renderBacktest(payload.result);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Walk-Forward";
  }
}

document.getElementById("set-symbol-btn").addEventListener("click", setSelectedSymbol);
document.getElementById("run-backtest-btn").addEventListener("click", runBacktest);
document.getElementById("run-wf-btn").addEventListener("click", runWalkForward);

refreshStatus();
setInterval(refreshStatus, 15000);
