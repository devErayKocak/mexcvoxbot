import requests
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask
import time
import threading

app = Flask(__name__)

# === Telegram Ayarları ===
TELEGRAM_TOKEN = "7811297577:AAFDDdcbV7KwDejK04M25ggxYNUqTEEmBvM"
CHAT_ID = "1519003075"

def send_signal(symbol, tf, direction, tp, sl):
    emoji = "🟢" if direction=="LONG" else "🔴"
    message = f"""{emoji} {direction} | {symbol} | {tf}
🎯 TP: {tp*100:.1f}% | 🛑 SL: {sl*100:.1f}%
⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    print(f"[TELEGRAM] {symbol} {tf} {direction} → {r.status_code}")

# === Strateji Parametreleri ===
TP_PCT = 0.015
SL_PCT = 0.02
L = 20
wickMult = 1.2
vol_window = 20
volMult = 1.5

COINS_15M = [
    "FLOKI_USDT","SUI_USDT","ONDO_USDT","APT_USDT","STORJ_USDT",
    "TAKE_USDT","MOVE_USDT","WLFI_USDT","INJ_USDT","WLD_USDT",
    "HYPE_USDT","BNB_USDT","TIA_USDT","PUMPFUN_USDT","HOLO_USDT",
    "ARB_USDT","TONCOIN_USDT","NEAR_USDT","TAO_USDT","ETHFI_USDT",
    "SLF_USDT","MRLN_USDT","STREAMER_USDT"
]

COINS_1H = [
    "LTC_USDT","XLM_USDT","DOT_USDT","XRP_USDT","APT_USDT",
    "TAO_USDT","ONDO_USDT","FLOKI_USDT","NEAR_USDT","HYPE_USDT",
    "MANA_USDT","ARB_USDT","INJ_USDT","MOVE_USDT"
]

# === Data Fetch ===
def fetch_klines(symbol, interval="Min15", limit=200):
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&limit={limit}"
    r = requests.get(url)
    data = r.json()
    if "data" not in data or not data["data"]:
        return pd.DataFrame()
    df = pd.DataFrame(data["data"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.rename(columns={"open":"open","high":"high","low":"low","close":"close","vol":"vol"})

# === Strategy ===
def run_strategy(df, L=20, wickMult=1.2, vol_window=20, volMult=1.5):
    if len(df) < L+2:
        return None
    body   = (df["close"] - df["open"]).abs()
    lowerW = np.minimum(df["open"], df["close"]) - df["low"]
    upperW = df["high"] - np.maximum(df["open"], df["close"])
    prevLow  = df["low"].shift(1).rolling(L).min()
    prevHigh = df["high"].shift(1).rolling(L).max()
    sweepDn  = (df["low"] < prevLow) & (df["close"] > prevLow)
    sweepUp  = (df["high"] > prevHigh) & (df["close"] < prevHigh)
    wickOK_L = lowerW > body * wickMult
    wickOK_S = upperW > body * wickMult
    volOK = df["vol"] > df["vol"].rolling(vol_window).mean() * volMult
    longCond  = sweepDn & wickOK_L & volOK
    shortCond = sweepUp & wickOK_S & volOK
    if longCond.iloc[-1]:
        return ("LONG", df["time"].iloc[-1])
    elif shortCond.iloc[-1]:
        return ("SHORT", df["time"].iloc[-1])
    return None

# === Bot Loop ===
def bot_loop():
    print("🚀 Bot Railway üzerinde çalışıyor...")
    while True:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] Kontrol başlıyor...")

        for sym in COINS_15M:
            df = fetch_klines(sym, "Min15", 200)
            if df.empty:
                continue
            sig = run_strategy(df)
            if sig:
                direction, t = sig
                send_signal(sym, "15m", direction, TP_PCT, SL_PCT)
                print(f"[{sym} 15m] Sinyal: {direction} @ {t}")

        for sym in COINS_1H:
            df = fetch_klines(sym, "Min60", 200)
            if df.empty:
                continue
            sig = run_strategy(df)
            if sig:
                direction, t = sig
                send_signal(sym, "1h", direction, TP_PCT, SL_PCT)
                print(f"[{sym} 1h] Sinyal: {direction} @ {t}")

        print(f"[{now}] Kontrol bitti.\n")
        time.sleep(60*15)

# === Railway endpoint ===
@app.route("/")
def home():
    return "Telegram sinyal botu Railway üzerinde çalışıyor ✅"

# Thread ile sürekli botu çalıştır
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
