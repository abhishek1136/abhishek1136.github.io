"""
═══════════════════════════════════════════════════════════
  STOCK ANALYSIS AGENT v2 — Daily Morning Brief
  Built for: Abhishek Nath | abhi.nath1136@gmail.com
  Market: NSE India | Source: Yahoo Finance (free)
  Features: Nifty 100, Top 5 Buy picks, Entry/SL/Target,
            Shares to buy, GitHub dashboard export
═══════════════════════════════════════════════════════════
"""

import yfinance as yf
import pandas as pd
import ta
import smtplib
import json
import re
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
import anthropic
from config import (GMAIL_APP_PASSWORD, ANTHROPIC_API_KEY, WATCHLIST,
                    EMAIL_TO, EMAIL_FROM, CAPITAL_PER_TRADE, RISK_PER_TRADE_PCT)

LOOKBACK_DAYS = "90d"


# ══════════════════════════════════════════════════════════
#  STEP 1 — FETCH & SCORE STOCKS
# ══════════════════════════════════════════════════════════

def fetch_stock_data(ticker_ns):
    try:
        tk = yf.Ticker(ticker_ns)
        df = tk.history(period=LOOKBACK_DAYS)
        if df.empty or len(df) < 30:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception as e:
        print("  ERROR fetching " + ticker_ns + ": " + str(e))
        return None


def compute_indicators(df):
    close  = df["Close"]
    volume = df["Volume"]

    try:
        rsi = round(float(ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]), 1)
    except Exception:
        rsi = None

    try:
        macd_obj  = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_val  = round(float(macd_obj.macd().iloc[-1]), 2)
        macd_sig  = round(float(macd_obj.macd_signal().iloc[-1]), 2)
        macd_hist = round(float(macd_obj.macd_diff().iloc[-1]), 2)
    except Exception:
        macd_val = macd_sig = macd_hist = None

    ma20  = round(float(close.rolling(20).mean().iloc[-1]), 2)
    ma50  = round(float(close.rolling(50).mean().iloc[-1]), 2)
    ma200 = round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else None

    try:
        bb_obj   = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_upper = round(float(bb_obj.bollinger_hband().iloc[-1]), 2)
        bb_lower = round(float(bb_obj.bollinger_lband().iloc[-1]), 2)
        bb_mid   = round(float(bb_obj.bollinger_mavg().iloc[-1]), 2)
    except Exception:
        bb_upper = bb_lower = bb_mid = None

    vol_today  = int(volume.iloc[-1])
    vol_avg20  = int(volume.rolling(20).mean().iloc[-1])
    vol_ratio  = round(vol_today / vol_avg20, 2) if vol_avg20 > 0 else None
    vol_spike  = vol_ratio is not None and vol_ratio >= 1.5

    last_close  = round(float(close.iloc[-1]), 2)
    prev_close  = round(float(close.iloc[-2]), 2)
    change_pct  = round(((last_close - prev_close) / prev_close) * 100, 2)
    week52_high = round(float(close.tail(252).max()), 2)
    week52_low  = round(float(close.tail(252).min()), 2)

    # ── Momentum score (0–100) for pre-filtering ──────────
    score = 0
    if rsi is not None:
        if 45 <= rsi <= 65:   score += 25   # sweet spot for swing entry
        elif 35 <= rsi < 45:  score += 15   # recovering
    if macd_hist is not None and macd_hist > 0:
        score += 20                          # MACD bullish crossover
    if last_close > ma20:     score += 15
    if last_close > ma50:     score += 20
    if vol_spike:             score += 20   # institutional interest

    return {
        "last_close": last_close, "prev_close": prev_close, "change_pct": change_pct,
        "week52_high": week52_high, "week52_low": week52_low,
        "rsi": rsi, "macd": macd_val, "macd_signal": macd_sig, "macd_hist": macd_hist,
        "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_mid": bb_mid,
        "vol_today": vol_today, "vol_avg20": vol_avg20,
        "vol_ratio": vol_ratio, "vol_spike": vol_spike,
        "momentum_score": score,
    }


# ══════════════════════════════════════════════════════════
#  STEP 2 — CLAUDE GENERATES STRUCTURED BRIEF
# ══════════════════════════════════════════════════════════

def parse_claude_json(raw):
    # Strip markdown fences
    raw = re.sub(r'^```json\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'^```\s*',     '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$',     '', raw, flags=re.MULTILINE).strip()

    # Extract outermost JSON object
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    # Fix trailing commas
    raw = re.sub(r',\s*([}\]])', r'\1', raw)

    # Strategy 1: direct parse
    try:
        return json.loads(raw)
    except Exception:
        pass

    # Strategy 2: replace smart quotes and special apostrophes
    raw2 = raw
    raw2 = raw2.replace('\u2018', "'").replace('\u2019', "'")
    raw2 = raw2.replace('\u201c', '"').replace('\u201d', '"')
    raw2 = raw2.replace('\u2013', '-').replace('\u2014', '-')
    try:
        return json.loads(raw2)
    except Exception:
        pass

    # Strategy 3: sanitize all string values — escape unescaped special chars
    # Replace unescaped single quotes inside JSON strings with escaped version
    raw3 = re.sub(r"(?<!\\)'", "\\'", raw2)
    try:
        return json.loads(raw3)
    except Exception:
        pass

    # Strategy 4: use json repair approach — remove problematic lines
    lines = raw.split('\n')
    clean_lines = []
    for line in lines:
        try:
            clean_line = line.encode('ascii', 'ignore').decode('ascii')
            clean_lines.append(clean_line)
        except Exception:
            clean_lines.append('')
    raw4 = '\n'.join(clean_lines)
    raw4 = re.sub(r',\s*([}\]])', r'\1', raw4)
    return json.loads(raw4)


def build_watchlist_locally(stock_data):
    """Build watchlist from indicators directly — no Claude needed."""
    watchlist = []
    for s in stock_data:
        rsi       = s.get("rsi") or 50
        score     = s.get("momentum_score", 0)
        macd_hist = s.get("macd_hist") or 0
        last      = s["last_close"]
        ma50      = s.get("ma50") or last
        if score >= 60 and last > ma50 and macd_hist > 0:
            signal = "BULLISH"
        elif score <= 25 or (last < ma50 and macd_hist < 0):
            signal = "BEARISH"
        elif score >= 40:
            signal = "WATCH"
        else:
            signal = "NEUTRAL"
        watchlist.append({
            "name": s["name"], "ticker": s["ticker"],
            "price": s["last_close"], "change_pct": s["change_pct"],
            "rsi": rsi, "signal": signal, "momentum_score": score,
        })
    return sorted(watchlist, key=lambda x: x["momentum_score"], reverse=True)


def generate_brief_with_claude(stock_data, capital, risk_pct):
    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today   = date.today().strftime("%A, %d %B %Y")
    ranked  = sorted(stock_data, key=lambda x: x.get("momentum_score", 0), reverse=True)
    top15   = ranked[:15]
    wl      = build_watchlist_locally(stock_data)

    # Stripped-down candidate list — only numbers, no long text
    candidates = []
    for s in top15:
        candidates.append({
            "name": s["name"].replace("'", "").replace("&", "and"),
            "ticker": s["ticker"],
            "price": s["last_close"],
            "change_pct": s["change_pct"],
            "rsi": s.get("rsi"),
            "macd_hist": s.get("macd_hist"),
            "ma50": s.get("ma50"),
            "vol_ratio": s.get("vol_ratio"),
            "score": s.get("momentum_score", 0),
            "vol_spike": s.get("vol_spike"),
        })

    schema = (
        '{"snapshot":"market overview under 50 words",'
        '"theme":"one sentence under 20 words",'
        '"beginner_tip":"one tip under 25 words",'
        '"alerts":["alert 1 under 20 words","alert 2"],'
        '"buy_picks":['
        '{"rank":1,"name":"StockName","ticker":"TICKER.NS","price":0.0,"change_pct":0.0,'
        '"entry_low":0.0,"entry_high":0.0,"stop_loss":0.0,"target_1":0.0,"target_2":0.0,'
        '"hold_days":"3-5","shares_to_buy":0,"capital_needed":0.0,"risk_amount":0.0,'
        '"conviction":"HIGH","why":"RSI 55 bullish MACD vol 1.8x above MA50"}'
        "]}"
    )
    prompt = (
        "You are an Indian equity analyst. Today: " + today + ". NSE 9:15 AM IST. "
        + "Capital Rs." + str(capital) + " Risk " + str(risk_pct) + "pct per trade. "
        + "Top candidates: " + json.dumps(candidates) + " "
        + "Return ONLY this JSON schema filled with real data. No markdown. ASCII only. No apostrophes. "
        + "Schema: " + schema + " "
        + "Rules: exactly 5 buy_picks BULLISH only. "
        + "shares_to_buy=int(" + str(capital) + "/entry_high). "
        + "stop_loss=entry_high*" + str(round(1 - risk_pct/100, 4)) + ". "
        + "capital_needed=shares_to_buy*entry_high. "
        + "risk_amount=(entry_high-stop_loss)*shares_to_buy. "
        + "conviction HIGH or MEDIUM. why max 10 words numbers only."
    )

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        brief = parse_claude_json(message.content[0].text)
        brief["watchlist"] = wl
        return brief
    except Exception as e:
        print("  WARNING: JSON parse failed (" + str(e) + "), using fallback")
        return {
            "snapshot": "Market data fetched for " + str(len(stock_data)) + " stocks.",
            "buy_picks": [], "alerts": ["AI brief unavailable today."],
            "watchlist": wl, "theme": "Review watchlist manually.",
            "beginner_tip": "Wait for the brief to generate correctly before trading."
        }


# ══════════════════════════════════════════════════════════
#  STEP 3 — BUILD HTML EMAIL
# ══════════════════════════════════════════════════════════

def sc(signal):
    return {"BULLISH":"#22c55e","BEARISH":"#ef4444","WATCH":"#f59e0b","NEUTRAL":"#64748b","HIGH":"#22c55e","MEDIUM":"#f59e0b"}.get(str(signal).upper(),"#64748b")

def sbg(signal):
    return {"BULLISH":"#052e16","BEARISH":"#450a0a","WATCH":"#451a03","NEUTRAL":"#1e293b","HIGH":"#052e16","MEDIUM":"#451a03"}.get(str(signal).upper(),"#1e293b")

def cc(pct):
    return "#22c55e" if float(pct) >= 0 else "#ef4444"

def arrow(pct):
    return "&#9650;" if float(pct) >= 0 else "&#9660;"


def build_html_email(brief, stock_data):
    today   = date.today().strftime("%d %B %Y")
    weekday = date.today().strftime("%A").upper()
    gainers = sum(1 for s in stock_data if s["change_pct"] > 0)
    losers  = len(stock_data) - gainers
    spikes  = sum(1 for s in stock_data if s.get("vol_spike"))

    # ── Buy Picks cards ───────────────────────────────────
    picks_html = ""
    for p in brief.get("buy_picks", []):
        conv_color = sc(p.get("conviction","MEDIUM"))
        conv_bg    = sbg(p.get("conviction","MEDIUM"))
        price_cc   = cc(p.get("change_pct", 0))
        price_arr  = arrow(p.get("change_pct", 0))
        picks_html += """
        <div style="background:#0d1f12;border:1px solid #166534;border-left:4px solid #22c55e;border-radius:10px;padding:22px 24px;margin-bottom:16px;">

          <!-- Header row -->
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;">
            <div>
              <span style="font-size:11px;color:#4ade80;letter-spacing:2px;font-weight:700;">#{rank} BUY PICK</span>
              <div style="font-size:20px;font-weight:800;color:#f0fdf4;margin-top:4px;">{name}</div>
              <div style="font-size:12px;color:#4b5563;">{ticker}</div>
            </div>
            <span style="background:{conv_bg};color:{conv_color};border:1px solid {conv_color};padding:5px 14px;border-radius:20px;font-size:12px;font-weight:700;letter-spacing:1px;">{conviction} CONVICTION</span>
          </div>

          <!-- Price row -->
          <div style="margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #14532d;">
            <span style="font-size:24px;font-weight:800;color:#f0fdf4;">&#8377;{price:,.2f}</span>
            <span style="font-size:14px;color:{price_cc};margin-left:10px;">{price_arr} {change_pct:+.2f}%</span>
          </div>

          <!-- Trade plan grid -->
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px;">
            <div style="background:#052e16;border:1px solid #166534;border-radius:8px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#4b5563;letter-spacing:1px;margin-bottom:4px;">ENTRY RANGE</div>
              <div style="font-size:13px;font-weight:700;color:#4ade80;">&#8377;{entry_low:,.0f}–{entry_high:,.0f}</div>
            </div>
            <div style="background:#450a0a;border:1px solid #7f1d1d;border-radius:8px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#4b5563;letter-spacing:1px;margin-bottom:4px;">STOP LOSS</div>
              <div style="font-size:13px;font-weight:700;color:#f87171;">&#8377;{stop_loss:,.0f}</div>
            </div>
            <div style="background:#0c1a3a;border:1px solid #1e3a8a;border-radius:8px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#4b5563;letter-spacing:1px;margin-bottom:4px;">HOLD</div>
              <div style="font-size:13px;font-weight:700;color:#60a5fa;">{hold_days} days</div>
            </div>
          </div>

          <!-- Targets row -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
            <div style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#4b5563;letter-spacing:1px;margin-bottom:4px;">TARGET 1 (conservative)</div>
              <div style="font-size:15px;font-weight:700;color:#34d399;">&#8377;{target_1:,.0f}</div>
            </div>
            <div style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#4b5563;letter-spacing:1px;margin-bottom:4px;">TARGET 2 (stretch)</div>
              <div style="font-size:15px;font-weight:700;color:#6ee7b7;">&#8377;{target_2:,.0f}</div>
            </div>
          </div>

          <!-- Capital breakdown -->
          <div style="background:#0a0f1e;border:1px solid #1e293b;border-radius:8px;padding:12px;margin-bottom:16px;display:flex;justify-content:space-between;">
            <div style="text-align:center;">
              <div style="font-size:10px;color:#4b5563;letter-spacing:1px;">SHARES</div>
              <div style="font-size:16px;font-weight:700;color:#e2e8f0;">{shares_to_buy}</div>
            </div>
            <div style="text-align:center;">
              <div style="font-size:10px;color:#4b5563;letter-spacing:1px;">CAPITAL NEEDED</div>
              <div style="font-size:16px;font-weight:700;color:#e2e8f0;">&#8377;{capital_needed:,.0f}</div>
            </div>
            <div style="text-align:center;">
              <div style="font-size:10px;color:#4b5563;letter-spacing:1px;">MAX RISK</div>
              <div style="font-size:16px;font-weight:700;color:#f87171;">&#8377;{risk_amount:,.0f}</div>
            </div>
          </div>

          <!-- Why -->
          <div style="font-size:13px;color:#86efac;line-height:1.7;background:#052e16;border-left:3px solid #22c55e;padding:12px 16px;border-radius:0 6px 6px 0;">
            {why}
          </div>
        </div>""".format(
            rank=p.get("rank","-"),
            name=p.get("name",""), ticker=p.get("ticker",""),
            price=float(p.get("price",0)),
            price_cc=price_cc, price_arr=price_arr,
            change_pct=float(p.get("change_pct",0)),
            conv_color=conv_color, conv_bg=conv_bg,
            conviction=p.get("conviction","MEDIUM"),
            entry_low=float(p.get("entry_low",0)),
            entry_high=float(p.get("entry_high",0)),
            stop_loss=float(p.get("stop_loss",0)),
            hold_days=p.get("hold_days","3-5"),
            target_1=float(p.get("target_1",0)),
            target_2=float(p.get("target_2",0)),
            shares_to_buy=p.get("shares_to_buy",0),
            capital_needed=float(p.get("capital_needed",0)),
            risk_amount=float(p.get("risk_amount",0)),
            why=p.get("why","")
        )

    # ── Beginner tip ──────────────────────────────────────
    tip = brief.get("beginner_tip", "")
    tip_html = ""
    if tip:
        tip_html = """
    <div style="margin-bottom:28px;">
      <div style="font-size:11px;color:#f59e0b;letter-spacing:3px;font-weight:700;margin-bottom:12px;">&#127891; BEGINNER TIP FOR TODAY</div>
      <div style="font-size:14px;color:#fde68a;line-height:1.8;background:#1c1008;border:1px solid #92400e;border-radius:8px;padding:16px 20px;">{}</div>
    </div>""".format(tip)

    # ── Alerts ────────────────────────────────────────────
    alerts_html = ""
    for a in brief.get("alerts", []):
        alerts_html += """
        <div style="display:flex;gap:12px;padding:12px 16px;background:#1c1008;border:1px solid #92400e;border-radius:8px;margin-bottom:8px;">
          <span style="font-size:16px;flex-shrink:0;">&#9888;&#65039;</span>
          <span style="font-size:13px;color:#fbbf24;line-height:1.5;">{}</span>
        </div>""".format(a)
    if not alerts_html:
        alerts_html = '<div style="font-size:13px;color:#475569;padding:12px;">No alerts today.</div>'

    # ── Watchlist table ───────────────────────────────────
    watchlist_sorted = sorted(brief.get("watchlist", []), key=lambda x: x.get("momentum_score", 0), reverse=True)
    rows_html = ""
    for i, w in enumerate(watchlist_sorted):
        bg     = "#0f172a" if i % 2 == 0 else "#111827"
        c_col  = cc(w.get("change_pct", 0))
        arr    = arrow(w.get("change_pct", 0))
        s_col  = sc(w.get("signal","NEUTRAL"))
        rsi    = float(w.get("rsi") or 0)
        rsi_color = "#ef4444" if rsi > 70 else ("#22c55e" if rsi < 30 else "#94a3b8")
        score  = w.get("momentum_score", 0)
        score_color = "#22c55e" if score >= 60 else ("#f59e0b" if score >= 35 else "#ef4444")
        rows_html += """
        <tr style="background:{bg};">
          <td style="padding:9px 12px;font-size:12px;font-weight:600;color:#e2e8f0;">{name}</td>
          <td style="padding:9px 12px;font-size:12px;color:#f1f5f9;text-align:right;">&#8377;{price:,.2f}</td>
          <td style="padding:9px 12px;font-size:12px;color:{c_col};text-align:right;">{arr} {change_pct:+.2f}%</td>
          <td style="padding:9px 12px;font-size:12px;color:{rsi_color};text-align:center;">{rsi:.0f}</td>
          <td style="padding:9px 12px;text-align:center;"><span style="color:{s_col};font-size:11px;font-weight:700;">{signal}</span></td>
          <td style="padding:9px 12px;text-align:center;"><span style="color:{score_color};font-size:12px;font-weight:700;">{score}</span></td>
        </tr>""".format(
            bg=bg, name=w.get("name",""), price=float(w.get("price",0)),
            c_col=c_col, arr=arr, change_pct=float(w.get("change_pct",0)),
            rsi_color=rsi_color, rsi=rsi,
            s_col=s_col, signal=w.get("signal",""), score_color=score_color, score=score
        )

    return """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Morning Market Brief</title></head>
<body style="margin:0;padding:20px 0;background:#030712;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:680px;margin:0 auto;">

  <!-- HEADER -->
  <div style="background:linear-gradient(135deg,#0f2027,#203a43,#0d2818);border-radius:14px 14px 0 0;padding:32px 36px;position:relative;overflow:hidden;">
    <div style="position:absolute;top:-30px;right:-30px;width:160px;height:160px;background:radial-gradient(circle,rgba(34,197,94,0.12),transparent 70%);border-radius:50%;"></div>
    <div style="font-size:11px;color:#4ade80;letter-spacing:3px;font-weight:600;margin-bottom:6px;">{weekday} &middot; NSE INDIA &middot; SWING TRADING BRIEF</div>
    <div style="font-size:26px;font-weight:800;color:#f0fdf4;letter-spacing:-0.5px;margin-bottom:4px;">&#127381; Morning Market Brief</div>
    <div style="font-size:14px;color:#6b7280;">{today} &middot; {total} stocks analysed &middot; Top 5 picks ready</div>
  </div>

  <!-- STATS BAR -->
  <div style="display:flex;background:#0f172a;border-left:1px solid #1e293b;border-right:1px solid #1e293b;">
    <div style="flex:1;padding:14px;text-align:center;border-right:1px solid #1e293b;">
      <div style="font-size:26px;font-weight:800;color:#22c55e;">{gainers}</div>
      <div style="font-size:10px;color:#374151;letter-spacing:2px;">GAINERS</div>
    </div>
    <div style="flex:1;padding:14px;text-align:center;border-right:1px solid #1e293b;">
      <div style="font-size:26px;font-weight:800;color:#ef4444;">{losers}</div>
      <div style="font-size:10px;color:#374151;letter-spacing:2px;">LOSERS</div>
    </div>
    <div style="flex:1;padding:14px;text-align:center;border-right:1px solid #1e293b;">
      <div style="font-size:26px;font-weight:800;color:#f59e0b;">{spikes}</div>
      <div style="font-size:10px;color:#374151;letter-spacing:2px;">VOL SPIKES</div>
    </div>
    <div style="flex:1;padding:14px;text-align:center;">
      <div style="font-size:26px;font-weight:800;color:#60a5fa;">{total}</div>
      <div style="font-size:10px;color:#374151;letter-spacing:2px;">ANALYSED</div>
    </div>
  </div>

  <!-- BODY -->
  <div style="background:#0a0f1e;border:1px solid #1e293b;border-top:none;border-bottom:none;padding:28px 32px;">

    <!-- Snapshot -->
    <div style="margin-bottom:28px;">
      <div style="font-size:11px;color:#f59e0b;letter-spacing:3px;font-weight:700;margin-bottom:12px;">&#128200; MARKET SNAPSHOT</div>
      <div style="font-size:15px;color:#cbd5e1;line-height:1.8;background:#0f172a;border-left:3px solid #22c55e;padding:16px 20px;border-radius:0 8px 8px 0;">{snapshot}</div>
    </div>

    <!-- Buy Picks -->
    <div style="margin-bottom:28px;">
      <div style="font-size:11px;color:#f59e0b;letter-spacing:3px;font-weight:700;margin-bottom:6px;">&#128994; TOP 5 BUY PICKS — PLACE AT 9:15 AM</div>
      <div style="font-size:12px;color:#374151;margin-bottom:16px;">Entry range = limit order price. Always set stop loss before buying.</div>
      {picks_html}
    </div>

    <!-- Beginner tip -->
    {tip_html}

    <!-- Alerts -->
    <div style="margin-bottom:28px;">
      <div style="font-size:11px;color:#f59e0b;letter-spacing:3px;font-weight:700;margin-bottom:12px;">&#9888;&#65039; ALERTS</div>
      {alerts_html}
    </div>

    <!-- Theme -->
    <div style="margin-bottom:28px;">
      <div style="font-size:11px;color:#f59e0b;letter-spacing:3px;font-weight:700;margin-bottom:12px;">&#128161; TODAY'S THEME</div>
      <div style="font-size:15px;color:#e2e8f0;line-height:1.7;font-style:italic;background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:16px 20px;">{theme}</div>
    </div>

    <!-- Full Watchlist -->
    <div>
      <div style="font-size:11px;color:#f59e0b;letter-spacing:3px;font-weight:700;margin-bottom:6px;">&#128203; FULL WATCHLIST — SORTED BY MOMENTUM</div>
      <div style="font-size:11px;color:#374151;margin-bottom:14px;">Score = 0-100. Higher = more indicators aligned bullish.</div>
      <div style="border-radius:10px;overflow:hidden;border:1px solid #1e293b;">
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
          <thead>
            <tr style="background:#1e293b;">
              <th style="padding:10px 12px;font-size:10px;color:#64748b;letter-spacing:1px;text-align:left;">STOCK</th>
              <th style="padding:10px 12px;font-size:10px;color:#64748b;letter-spacing:1px;text-align:right;">PRICE</th>
              <th style="padding:10px 12px;font-size:10px;color:#64748b;letter-spacing:1px;text-align:right;">CHANGE</th>
              <th style="padding:10px 12px;font-size:10px;color:#64748b;letter-spacing:1px;text-align:center;">RSI</th>
              <th style="padding:10px 12px;font-size:10px;color:#64748b;letter-spacing:1px;text-align:center;">SIGNAL</th>
              <th style="padding:10px 12px;font-size:10px;color:#64748b;letter-spacing:1px;text-align:center;">SCORE</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- FOOTER -->
  <div style="background:#030712;border:1px solid #1e293b;border-top:none;border-radius:0 0 14px 14px;padding:20px 32px;text-align:center;">
    <div style="font-size:11px;color:#374151;border-top:1px solid #1e293b;padding-top:16px;">
      Stock Analysis Agent &middot; {today} &middot; For informational purposes only. Not financial advice. Always use stop losses.
    </div>
  </div>

</div>
</body>
</html>""".format(
        weekday=weekday, today=today, total=len(stock_data),
        gainers=gainers, losers=losers, spikes=spikes,
        snapshot=brief.get("snapshot",""),
        picks_html=picks_html, tip_html=tip_html,
        alerts_html=alerts_html,
        theme=brief.get("theme",""),
        rows_html=rows_html,
    )


# ══════════════════════════════════════════════════════════
#  STEP 4 — SAVE data.json FOR GITHUB DASHBOARD
# ══════════════════════════════════════════════════════════

def save_dashboard_json(brief, stock_data):
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date.today().strftime("%d %B %Y"),
        "weekday": date.today().strftime("%A"),
        "stats": {
            "total": len(stock_data),
            "gainers": sum(1 for s in stock_data if s["change_pct"] > 0),
            "losers":  sum(1 for s in stock_data if s["change_pct"] < 0),
            "vol_spikes": sum(1 for s in stock_data if s.get("vol_spike")),
        },
        "snapshot": brief.get("snapshot",""),
        "theme":    brief.get("theme",""),
        "beginner_tip": brief.get("beginner_tip",""),
        "buy_picks": brief.get("buy_picks",[]),
        "alerts":    brief.get("alerts",[]),
        "watchlist": brief.get("watchlist",[]),
    }
    out_path = os.path.join(os.path.dirname(__file__), "data.json")
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print("  OK  data.json saved -> " + out_path)
    return payload


# ══════════════════════════════════════════════════════════
#  STEP 5 — SEND EMAIL
# ══════════════════════════════════════════════════════════

def send_email(subject, html_content, plain_text):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_content, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print("  OK  Email sent to " + EMAIL_TO)


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

def main():
    print("\n" + "="*55)
    print("  STOCK ANALYSIS AGENT v2 - Starting...")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("  Analysing " + str(len(WATCHLIST)) + " stocks")
    print("="*55 + "\n")

    stock_data = []
    for name, ticker in WATCHLIST.items():
        print("  Fetching " + name + " (" + ticker + ")...")
        df = fetch_stock_data(ticker)
        if df is None:
            continue
        ind = compute_indicators(df)
        ind["name"]   = name
        ind["ticker"] = ticker
        stock_data.append(ind)
        sign = "+" if ind["change_pct"] >= 0 else ""
        print("  OK  " + name + ": Rs." + str(ind["last_close"]) +
              " (" + sign + str(ind["change_pct"]) + "%) | RSI:" +
              str(ind["rsi"]) + " | Score:" + str(ind["momentum_score"]))

    if not stock_data:
        print("  ERROR: No data fetched.")
        return

    print("\n  Fetched " + str(len(stock_data)) + " stocks | Generating brief with Claude AI...\n")

    try:
        brief = generate_brief_with_claude(stock_data, CAPITAL_PER_TRADE, RISK_PER_TRADE_PCT)
        print("  OK  Brief generated\n")
    except Exception as e:
        print("  ERROR - Claude API: " + str(e))
        return

    # Save JSON for GitHub dashboard
    save_dashboard_json(brief, stock_data)

    # Send email
    print("  Sending email...")
    today_str = date.today().strftime("%d %b %Y")
    subject   = "Top 5 Picks + Morning Brief - " + today_str
    plain     = brief.get("snapshot","") + "\n\n" + brief.get("theme","")
    html      = build_html_email(brief, stock_data)
    send_email(subject, html, plain)

    print("\n" + "="*55)
    print("  DONE! Brief delivered.")
    print("  Next: push data.json to GitHub for live dashboard.")
    print("="*55 + "\n")


if __name__ == "__main__":
    main()
