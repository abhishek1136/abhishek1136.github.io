"""
═══════════════════════════════════════════════════════════
  CONFIGURATION
  - Locally: fill in the values below directly
  - GitHub Actions (cloud): values are read from repo Secrets
    (you never paste keys into this file for cloud runs)
═══════════════════════════════════════════════════════════
"""

import os

# ── Credentials ────────────────────────────────────────────
# When running via GitHub Actions, these come from repo Secrets.
# When running locally, paste your values here as fallback.
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY",  "sk-ant-...")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")

# ── Email ──────────────────────────────────────────────────
EMAIL_FROM = "abhi.nath1136@gmail.com"
EMAIL_TO   = "abhi.nath1136@gmail.com"

# ── Trading Profile ────────────────────────────────────────
CAPITAL_PER_TRADE  = 25000   # ₹ per trade
RISK_PER_TRADE_PCT = 2       # % max loss per trade

# ── Nifty 100 Watchlist ────────────────────────────────────
WATCHLIST = {
    # Nifty 50 core
    "Reliance Industries":  "RELIANCE.NS",
    "TCS":                  "TCS.NS",
    "HDFC Bank":            "HDFCBANK.NS",
    "Infosys":              "INFY.NS",
    "ICICI Bank":           "ICICIBANK.NS",
    "Kotak Mahindra Bank":  "KOTAKBANK.NS",
    "Larsen & Toubro":      "LT.NS",
    "Bajaj Finance":        "BAJFINANCE.NS",
    "Hindustan Unilever":   "HINDUNILVR.NS",
    "Axis Bank":            "AXISBANK.NS",
    "State Bank of India":  "SBIN.NS",
    "Maruti Suzuki":        "MARUTI.NS",
    "Sun Pharma":           "SUNPHARMA.NS",
    "Tata Motors":          "TATAMOTORS.NS",
    "Wipro":                "WIPRO.NS",
    "Asian Paints":         "ASIANPAINT.NS",
    "ITC":                  "ITC.NS",
    "HCL Technologies":     "HCLTECH.NS",
    "Power Grid":           "POWERGRID.NS",
    "Adani Ports":          "ADANIPORTS.NS",
    # Nifty Next 50
    "Tata Steel":           "TATASTEEL.NS",
    "JSW Steel":            "JSWSTEEL.NS",
    "NTPC":                 "NTPC.NS",
    "Bajaj Auto":           "BAJAJ-AUTO.NS",
    "Titan Company":        "TITAN.NS",
    "UltraTech Cement":     "ULTRACEMCO.NS",
    "Nestle India":         "NESTLEIND.NS",
    "Divi's Labs":          "DIVISLAB.NS",
    "Cipla":                "CIPLA.NS",
    "Dr Reddy's":           "DRREDDY.NS",
    "Tata Consumer":        "TATACONSUM.NS",
    "Hindalco":             "HINDALCO.NS",
    "Vedanta":              "VEDL.NS",
    "ONGC":                 "ONGC.NS",
    "Coal India":           "COALINDIA.NS",
    "BPCL":                 "BPCL.NS",
    "IndusInd Bank":        "INDUSINDBK.NS",
    "Shriram Finance":      "SHRIRAMFIN.NS",
    "Godrej Consumer":      "GODREJCP.NS",
    "Dabur India":          "DABUR.NS",
    "Marico":               "MARICO.NS",
    "Havells India":        "HAVELLS.NS",
    "Voltas":               "VOLTAS.NS",
    "Pidilite Industries":  "PIDILITIND.NS",
    "Tata Power":           "TATAPOWER.NS",
    "Adani Enterprises":    "ADANIENT.NS",
    "Adani Green":          "ADANIGREEN.NS",
    "Apollo Hospitals":     "APOLLOHOSP.NS",
    "Max Healthcare":       "MAXHEALTH.NS",
    "Zomato":               "ZOMATO.NS",
}
