#!/usr/bin/env python3
"""
Generate dashboard.html — standalone trade log viewer.
Merges trades.json + performance_log.json (if present) by order_id.
Usage:  python3 generate_dashboard.py
Output: dashboard.html  (open in any browser)
"""

import json
import os
from datetime import datetime

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(BASE_DIR, "trades.json")
PERF_FILE   = os.path.join(BASE_DIR, "performance_log.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "dashboard.html")


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _parse_dt(ts):
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except Exception:
        return (ts[:10] if ts else ""), ""


def merge_trades():
    trades   = _load(TRADES_FILE)
    perf_log = _load(PERF_FILE)
    perf_idx = {e["order_id"]: e for e in perf_log if "order_id" in e}

    merged = []
    for t in trades:
        oid  = t.get("order_id", "")
        perf = perf_idx.get(oid, {})
        date, time = _parse_dt(t.get("timestamp", ""))
        merged.append({
            "symbol":        t.get("symbol", ""),
            "side":          t.get("side", ""),
            "qty":           t.get("qty", 0),
            "entry_price":   t.get("entry_price"),
            "stop_loss":     t.get("stop_loss"),
            "take_profit":   t.get("take_profit"),
            "date":          date,
            "time":          time,
            "timestamp":     t.get("timestamp", ""),
            "order_id":      oid,
            "trade_status":  t.get("status", ""),
            "perf_status":   perf.get("status", ""),
            "exit_price":    perf.get("exit_price"),
            "exit_date":     perf.get("exit_date"),
            "pnl_pct":       perf.get("pnl_pct"),
            "outcome":       perf.get("outcome"),
            "advisor_votes": perf.get("advisor_votes", {}),
            "reasoning":     t.get("reasoning", ""),
        })

    merged.sort(key=lambda x: x["timestamp"], reverse=True)
    return merged


# ── HTML template ─────────────────────────────────────────────────────────────
# Placeholders: __DATA_JSON__  __TOTAL__  __BUYS__  __SELLS__
#               __CLOSED__  __WIN_RATE__  __WIN_RATE_CLS__  __GENERATED_AT__
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alpaca Trader — Trade Log</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

:root{
  --bg:#020617;
  --s1:#0F172A;
  --s2:#1E293B;
  --bd:#1E293B;
  --bd2:#334155;
  --tx:#F8FAFC;
  --tx2:#94A3B8;
  --tx3:#475569;
  --grn:#22C55E;
  --red:#EF5350;
  --blu:#3B82F6;
  --yel:#F59E0B;
  --grn-d:rgba(34,197,94,.1);
  --red-d:rgba(239,83,80,.1);
  --blu-d:rgba(59,130,246,.1);
  --grn-glow:0 0 24px rgba(34,197,94,.22);
  --red-glow:0 0 24px rgba(239,83,80,.22);
  --ease:200ms cubic-bezier(.4,0,.2,1);
}

body{
  background:var(--bg);color:var(--tx);
  font-family:'Fira Sans',system-ui,sans-serif;
  font-size:14px;line-height:1.6;min-height:100vh;
}

/* ── header ─────────────────────────────────────────────────────── */
.hdr{
  position:sticky;top:0;z-index:30;
  display:flex;align-items:center;justify-content:space-between;
  padding:18px 24px;
  background:rgba(2,6,23,.88);
  border-bottom:1px solid var(--bd);
  backdrop-filter:blur(16px);
}
.hdr-left{display:flex;align-items:center;gap:10px}
.dot{
  width:8px;height:8px;border-radius:50%;
  background:var(--grn);box-shadow:var(--grn-glow);
  animation:blink 2.5s ease infinite;
}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
.hdr h1{
  font-family:'Fira Code',monospace;
  font-size:14px;font-weight:600;letter-spacing:.06em;
}
.hdr-ts{font-family:'Fira Code',monospace;font-size:11px;color:var(--tx3)}

/* ── kpi strip ───────────────────────────────────────────────────── */
.kpi{
  display:grid;
  grid-template-columns:repeat(5,1fr);
  border-bottom:1px solid var(--bd);
}
@media(max-width:540px){.kpi{grid-template-columns:repeat(3,1fr)}}
.kpi-cell{
  padding:18px 20px;
  border-right:1px solid var(--bd);
}
.kpi-cell:last-child{border-right:none}
.kpi-lbl{
  display:block;
  font-size:10px;font-weight:500;
  letter-spacing:.12em;text-transform:uppercase;
  color:var(--tx3);margin-bottom:5px;
}
.kpi-val{
  display:block;
  font-family:'Fira Code',monospace;
  font-size:26px;font-weight:700;line-height:1;
}
.kpi-val.grn{color:var(--grn);text-shadow:var(--grn-glow)}
.kpi-val.red{color:var(--red)}
.kpi-val.dim{color:var(--tx2)}

/* ── controls ────────────────────────────────────────────────────── */
.ctrl{
  position:sticky;top:61px;z-index:20;
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:12px 24px;
  background:rgba(2,6,23,.92);
  border-bottom:1px solid var(--bd);
  backdrop-filter:blur(12px);
}
.pg{
  display:flex;gap:3px;
  background:var(--s1);border:1px solid var(--bd);
  border-radius:8px;padding:3px;
}
.pill{
  padding:5px 13px;border-radius:6px;
  border:none;background:transparent;
  color:var(--tx3);
  font-family:'Fira Sans',sans-serif;
  font-size:12px;font-weight:500;
  cursor:pointer;
  transition:all var(--ease);
}
.pill:hover{color:var(--tx);background:var(--s2)}
.pill.on{background:var(--s2);color:var(--tx);font-weight:600}
.pill[data-v=buy].on{color:var(--grn)}
.pill[data-v=sell].on{color:var(--red)}
.cnt{font-family:'Fira Code',monospace;font-size:11px;color:var(--tx3)}
.srt{
  margin-left:auto;
  background:var(--s1);border:1px solid var(--bd);
  color:var(--tx2);
  font-family:'Fira Sans',sans-serif;font-size:12px;
  padding:6px 10px;border-radius:8px;
  cursor:pointer;outline:none;
  transition:border-color var(--ease),color var(--ease);
}
.srt:focus,.srt:hover{border-color:var(--bd2);color:var(--tx)}
.srt option{background:var(--s1)}

/* ── trade list ──────────────────────────────────────────────────── */
.list{
  padding:16px 24px;
  display:flex;flex-direction:column;gap:8px;
  max-width:1100px;margin:0 auto;
}

/* ── trade card ──────────────────────────────────────────────────── */
.card{
  background:var(--s1);
  border:1px solid var(--bd);
  border-radius:12px;overflow:hidden;
  transition:border-color var(--ease),box-shadow var(--ease);
}
.card:hover{border-color:var(--bd2)}
.card.buy:hover{box-shadow:var(--grn-glow)}
.card.sell:hover{box-shadow:var(--red-glow)}

.card-main{
  display:grid;
  grid-template-columns:44px 1fr auto auto auto auto;
  align-items:center;gap:16px;
  padding:16px 20px;
}
@media(max-width:680px){
  .card-main{grid-template-columns:44px 1fr auto auto}
  .c-price,.c-qty{display:none}
}

/* side badge */
.badge{
  width:44px;height:44px;border-radius:10px;
  display:flex;align-items:center;justify-content:center;
  font-family:'Fira Code',monospace;
  font-size:9px;font-weight:700;letter-spacing:.1em;
  flex-shrink:0;
}
.badge.buy{background:var(--grn-d);color:var(--grn);border:1px solid rgba(34,197,94,.2)}
.badge.sell{background:var(--red-d);color:var(--red);border:1px solid rgba(239,83,80,.2)}

/* symbol */
.c-sym{display:flex;flex-direction:column;gap:2px;min-width:0}
.sym{
  font-family:'Fira Code',monospace;
  font-size:18px;font-weight:700;letter-spacing:.04em;
}
.sym-dt{font-family:'Fira Code',monospace;font-size:11px;color:var(--tx3)}

/* price */
.c-price{display:flex;flex-direction:column;gap:3px;text-align:right}
.price{font-family:'Fira Code',monospace;font-size:16px;font-weight:600}
.price-sub{font-family:'Fira Code',monospace;font-size:10px;color:var(--tx3)}

/* qty */
.c-qty{display:flex;flex-direction:column;align-items:center;gap:1px}
.qty{font-family:'Fira Code',monospace;font-size:15px;font-weight:600;color:var(--tx2)}
.qty-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--tx3)}

/* pnl */
.c-pnl{text-align:right;min-width:68px}
.pnl{font-family:'Fira Code',monospace;font-size:16px;font-weight:700}
.pnl.win{color:var(--grn);text-shadow:var(--grn-glow)}
.pnl.loss{color:var(--red)}
.pnl.none{font-size:12px;font-weight:400;color:var(--tx3)}
.pnl-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--tx3)}

/* status chip */
.chip{
  padding:3px 9px;border-radius:20px;
  font-family:'Fira Code',monospace;
  font-size:10px;font-weight:600;
  letter-spacing:.08em;text-transform:uppercase;
  white-space:nowrap;
}
.chip.open{background:var(--blu-d);color:var(--blu);border:1px solid rgba(59,130,246,.25)}
.chip.win{background:var(--grn-d);color:var(--grn);border:1px solid rgba(34,197,94,.25)}
.chip.loss{background:var(--red-d);color:var(--red);border:1px solid rgba(239,83,80,.25)}
.chip.pending{background:rgba(245,158,11,.08);color:var(--yel);border:1px solid rgba(245,158,11,.2)}

/* ── reasoning section ───────────────────────────────────────────── */
.rw{border-top:1px solid var(--bd)}

.rtoggle{
  display:flex;align-items:center;gap:8px;
  width:100%;padding:10px 20px;
  background:none;border:none;
  color:var(--tx3);
  font-family:'Fira Sans',sans-serif;font-size:12px;
  text-align:left;cursor:pointer;
  transition:color var(--ease);
}
.rtoggle:hover{color:var(--tx2)}
.rtoggle:focus-visible{outline:2px solid var(--grn);outline-offset:-2px;border-radius:4px}

.chev{
  width:14px;height:14px;flex-shrink:0;
  transition:transform var(--ease);
}
.rtoggle[aria-expanded=true] .chev{transform:rotate(180deg)}

.preview{
  flex:1;min-width:0;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  font-style:italic;
}

.rbody{
  max-height:0;overflow:hidden;
  transition:max-height 320ms cubic-bezier(.4,0,.2,1);
}
.rbody.open{max-height:400px}

.rtxt{
  padding:4px 20px 14px;
  color:var(--tx2);font-size:13px;line-height:1.75;
  font-style:italic;
}

/* ── advisor votes ───────────────────────────────────────────────── */
.votes{
  display:flex;gap:5px;flex-wrap:wrap;
  padding:0 20px 14px;
}
.vote{
  padding:2px 8px;border-radius:4px;
  font-family:'Fira Code',monospace;font-size:10px;
  border:1px solid var(--bd2);color:var(--tx3);
}
.vote.buy{background:var(--grn-d);color:var(--grn);border-color:rgba(34,197,94,.2)}
.vote.sell{background:var(--red-d);color:var(--red);border-color:rgba(239,83,80,.2)}

/* ── empty ───────────────────────────────────────────────────────── */
.empty{
  text-align:center;padding:80px 24px;
  color:var(--tx3);
  font-family:'Fira Code',monospace;font-size:13px;
}

/* ── scrollbar ───────────────────────────────────────────────────── */
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:3px}

@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{transition:none!important;animation:none!important}
}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-left">
    <div class="dot" aria-hidden="true"></div>
    <h1>ALPACA_TRADER / trade-log</h1>
  </div>
  <span class="hdr-ts">generated __GENERATED_AT__</span>
</header>

<div class="kpi" role="region" aria-label="Summary statistics">
  <div class="kpi-cell">
    <span class="kpi-lbl">Total</span>
    <span class="kpi-val">__TOTAL__</span>
  </div>
  <div class="kpi-cell">
    <span class="kpi-lbl">Buys</span>
    <span class="kpi-val grn">__BUYS__</span>
  </div>
  <div class="kpi-cell">
    <span class="kpi-lbl">Sells</span>
    <span class="kpi-val red">__SELLS__</span>
  </div>
  <div class="kpi-cell">
    <span class="kpi-lbl">Closed</span>
    <span class="kpi-val dim">__CLOSED__</span>
  </div>
  <div class="kpi-cell">
    <span class="kpi-lbl">Win Rate</span>
    <span class="kpi-val __WIN_RATE_CLS__">__WIN_RATE__</span>
  </div>
</div>

<div class="ctrl">
  <div class="pg" role="group" aria-label="Filter by side">
    <button class="pill on" data-v="all"  onclick="setF('side','all',this)">All</button>
    <button class="pill"    data-v="buy"  onclick="setF('side','buy',this)">Buy</button>
    <button class="pill"    data-v="sell" onclick="setF('side','sell',this)">Sell</button>
  </div>
  <div class="pg" role="group" aria-label="Filter by status">
    <button class="pill on" data-v="all"    onclick="setF('status','all',this)">All</button>
    <button class="pill"    data-v="open"   onclick="setF('status','open',this)">Open</button>
    <button class="pill"    data-v="closed" onclick="setF('status','closed',this)">Closed</button>
  </div>
  <span class="cnt" id="cnt" aria-live="polite"></span>
  <select class="srt" onchange="setSort(this.value)" aria-label="Sort trades">
    <option value="date-desc">Newest first</option>
    <option value="date-asc">Oldest first</option>
    <option value="symbol-asc">Symbol A–Z</option>
    <option value="pnl-desc">P&amp;L High → Low</option>
    <option value="pnl-asc">P&amp;L Low → High</option>
  </select>
</div>

<main class="list" id="list" aria-label="Trade log"></main>

<script>
const TRADES = __DATA_JSON__;
const state  = { side: 'all', status: 'all', sort: 'date-desc' };

function setF(type, val, btn) {
  state[type] = val;
  btn.closest('.pg').querySelectorAll('.pill').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  render();
}
function setSort(val) { state.sort = val; render(); }

function statusInfo(t) {
  if (t.perf_status === 'closed')
    return t.outcome === 'win' ? { cls:'win',  label:'WIN'  }
                               : { cls:'loss', label:'LOSS' };
  if (t.perf_status === 'open') return { cls:'open',    label:'OPEN'    };
  return { cls:'pending', label:(t.trade_status||'PENDING').toUpperCase() };
}

function fmt(n) {
  return n != null ? '$' + Number(n).toFixed(2) : '—';
}

function pnlBlock(t) {
  if (t.pnl_pct != null) {
    const cls  = t.outcome === 'win' ? 'win' : 'loss';
    const sign = t.pnl_pct > 0 ? '+' : '';
    return `<div class="pnl ${cls}">${sign}${t.pnl_pct}%</div><div class="pnl-lbl">P&L</div>`;
  }
  return `<div class="pnl none">—</div><div class="pnl-lbl">P&L</div>`;
}

function votesBlock(votes) {
  if (!votes || !Object.keys(votes).length) return '';
  const chips = Object.entries(votes).map(([adv, d]) => {
    const rec  = (d.recommendation || '').toLowerCase();
    const cls  = rec === 'buy' ? 'buy' : rec === 'sell' ? 'sell' : '';
    const name = adv.replace(/ Analyst| Manager| Strategist/g, '');
    const conf = d.confidence ? ` ${d.confidence}%` : '';
    return `<span class="vote ${cls}" title="${adv}: ${d.recommendation||''}">${name}${conf}</span>`;
  }).join('');
  return `<div class="votes">${chips}</div>`;
}

function firstSent(txt) {
  const m = txt.match(/[^.!?]+[.!?]/);
  return m ? m[0].trim() : txt.slice(0, 110) + (txt.length > 110 ? '…' : '');
}

function cardHTML(t, i) {
  const si   = statusInfo(t);
  const hasR = t.reasoning && t.reasoning.trim();
  const hasV = t.advisor_votes && Object.keys(t.advisor_votes).length;

  return `<article class="card ${t.side}">
  <div class="card-main">
    <div class="badge ${t.side}" aria-label="${t.side} trade">${t.side.toUpperCase()}</div>
    <div class="c-sym">
      <span class="sym">${t.symbol}</span>
      <span class="sym-dt">${t.date} · ${t.time}</span>
    </div>
    <div class="c-price">
      <span class="price">${fmt(t.entry_price)}</span>
      <span class="price-sub">SL ${fmt(t.stop_loss)} · TP ${fmt(t.take_profit)}</span>
    </div>
    <div class="c-qty">
      <span class="qty">${t.qty}</span>
      <span class="qty-lbl">shares</span>
    </div>
    <div class="c-pnl">${pnlBlock(t)}</div>
    <span class="chip ${si.cls}">${si.label}</span>
  </div>
  ${hasR ? `<div class="rw">
    <button class="rtoggle" aria-expanded="false"
            onclick="toggleR(this,'r${i}')" aria-controls="r${i}">
      <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="preview">${firstSent(t.reasoning)}</span>
    </button>
    <div class="rbody" id="r${i}" role="region" aria-label="Full reasoning for ${t.symbol}">
      <p class="rtxt">${t.reasoning}</p>
      ${hasV ? votesBlock(t.advisor_votes) : ''}
    </div>
  </div>` : ''}
</article>`;
}

function toggleR(btn, id) {
  const exp = btn.getAttribute('aria-expanded') === 'true';
  btn.setAttribute('aria-expanded', String(!exp));
  document.getElementById(id).classList.toggle('open', !exp);
}

function getList() {
  const fil = TRADES.filter(t => {
    if (state.side   !== 'all' && t.side        !== state.side)   return false;
    if (state.status === 'open'   && t.perf_status !== 'open')    return false;
    if (state.status === 'closed' && t.perf_status !== 'closed')  return false;
    return true;
  });

  return [...fil].sort((a, b) => {
    switch (state.sort) {
      case 'date-asc':   return a.timestamp.localeCompare(b.timestamp);
      case 'date-desc':  return b.timestamp.localeCompare(a.timestamp);
      case 'symbol-asc': return a.symbol.localeCompare(b.symbol);
      case 'pnl-desc':   return (b.pnl_pct ?? -Infinity) - (a.pnl_pct ?? -Infinity);
      case 'pnl-asc':    return (a.pnl_pct ?? Infinity)  - (b.pnl_pct ?? Infinity);
      default: return 0;
    }
  });
}

function render() {
  const list = getList();
  const el   = document.getElementById('list');
  document.getElementById('cnt').textContent = `${list.length} trade${list.length !== 1 ? 's' : ''}`;
  el.innerHTML = list.length
    ? list.map((t, i) => cardHTML(t, i)).join('')
    : '<div class="empty">No trades match the current filter.</div>';
}

render();
</script>
</body>
</html>"""


# ── assemble ──────────────────────────────────────────────────────────────────

def generate_html(trades):
    total  = len(trades)
    buys   = sum(1 for t in trades if t["side"] == "buy")
    sells  = sum(1 for t in trades if t["side"] == "sell")
    closed = sum(1 for t in trades if t.get("perf_status") == "closed")
    wins   = sum(1 for t in trades if t.get("outcome") == "win")

    if closed:
        rate     = f"{round(wins / closed * 100)}%"
        rate_cls = "grn" if wins / closed >= 0.5 else "red"
    else:
        rate, rate_cls = "—", "dim"

    return (HTML
        .replace("__DATA_JSON__",    json.dumps(trades))
        .replace("__TOTAL__",        str(total))
        .replace("__BUYS__",         str(buys))
        .replace("__SELLS__",        str(sells))
        .replace("__CLOSED__",       str(closed))
        .replace("__WIN_RATE__",     rate)
        .replace("__WIN_RATE_CLS__", rate_cls)
        .replace("__GENERATED_AT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
    )


if __name__ == "__main__":
    trades = merge_trades()
    html   = generate_html(trades)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated: {OUTPUT_FILE}")
    print(f"  {len(trades)} trades  ({sum(1 for t in trades if t['side']=='buy')} buys / {sum(1 for t in trades if t['side']=='sell')} sells)")
