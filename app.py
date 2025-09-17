import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timezone
from telegram import Bot

# === Telegram Ayarları ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7811297577:AAFDDdcbV7KwDejK04M25ggxYNUqTEEmBvM")
CHAT_ID = os.getenv("CHAT_ID", "1519003075")
bot = Bot(token=TELEGRAM_TOKEN)

# === Logger ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === Parametreler ===
TP_PCT = 0.015  # %1.5
SL_PCT = 0.02   # %2
VOL_WINDOW = 20
WICK_MULT = 1.2
LOOKBACK = 30

# === Coin listeleri ===
COINS_15M = [
    "FLOKI_USDT","SUI_USDT","ONDO_USDT","APT_USDT","STORJ_USDT","TAKE_USDT","MOVE_USDT",
    "WLFI_USDT","INJ_USDT","WLD_USDT","HYPE_USDT","BNB_USDT","TIA_USDT","PUMPFUN_USDT",
    "HOLO_USDT","ARB_USDT","TONCOIN_USDT","NEAR_USDT","TAO_USDT","ETHFI_USDT","SLF_USDT",
    "MRLN_USDT","STREAMER_USDT"
]

COINS_1H = [
    "LTC_USDT","XLM_USDT","XRP_USDT","APT_USDT","TAO_USDT","ONDO_USDT","DOT_USDT",
    "NEAR_USDT","HYPE_USDT","MANA_USDT","ARB_USDT","INJ_USDT","MOVE_USDT","FLOKI_USDT"
]

# === MEXC Kline verisi çek ===
def fetch_klines(symbol, interval="15m", limit=500):
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&limit={limit}"
    r = requests.get(url)
    data = r.json()
    if "data" not in data or len(data["data"]) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(data["data"])
    df["open_time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["vol"] = df["amount"].astype(float)
    return df[["open_time","open","high","low","close","vol"]]

# === Strateji ===
def run_strategy(df, sym):
    if df.empty or len(df) < LOOKBACK:
        return None

    last = df.iloc[-1]
    body = abs(last["close"] - last["open"])
    lower_wick = min(last["open"], last["close"]) - last["low"]
    upper_wick = last["high"] - max(last["open"], last["close"])

    prev_low = df["low"].iloc[-LOOKBACK:-1].min()
    prev_high = df["high"].iloc[-LOOKBACK:-1].max()

    sweep_down = last["low"] < prev_low and last["close"] > prev_low
    sweep_up = last["high"] > prev_high and last["close"] < prev_high
    wick_ok_long = lower_wick > body * WICK_MULT
    wick_ok_short = upper_wick > body * WICK_MULT
    vol_ok = last["vol"] > df["vol"].iloc[-VOL_WINDOW:].mean()

    long_signal = sweep_down and wick_ok_long and vol_ok
    short_signal = sweep_up and wick_ok_short and vol_ok

    if long_signal:
        sl = last["low"] * (1 - SL_PCT)
        tp = last["close"] * (1 + TP_PCT)
        return f"🟢 LONG | {sym}\nFiyat: {last['close']:.4f}\nTP: {tp:.4f} | SL: {sl:.4f}"
    elif short_signal:
        sl = last["high"] * (1 + SL_PCT)
        tp = last["close"] * (1 - TP_PCT)
        return f"🔴 SHORT | {sym}\nFiyat: {last['close']:.4f}\nTP: {tp:.4f} | SL: {sl:.4f}"
    return None

# === Bot döngüsü ===
def run_bot():
    while True:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"Yeni kontrol başladı: {now}")

        for sym in COINS_15M:
            try:
                df = fetch_klines(sym, "15m", 200)
                msg = run_strategy(df, sym)
                if msg:
                    bot.send_message(chat_id=CHAT_ID, text=f"[15m] {msg}")
                    logging.info(f"Sinyal gönderildi: {sym} (15m)")
            except Exception as e:
                logging.error(f"{sym} hata: {e}")

        for sym in COINS_1H:
            try:
                df = fetch_klines(sym, "1h", 200)
                msg = run_strategy(df, sym)
                if msg:
                    bot.send_message(chat_id=CHAT_ID, text=f"[1h] {msg}")
                    logging.info(f"Sinyal gönderildi: {sym} (1h)")
            except Exception as e:
                logging.error(f"{sym} hata: {e}")

        logging.info("Kontrol bitti, 5 dk bekleniyor...\n")
        time.sleep(300)

if __name__ == "__main__":
    run_bot()
