import logging
from telegram import Bot
from telegram.ext import Application

import asyncio
import requests
import pandas as pd
from datetime import datetime, timedelta

# === Telegram Ayarları ===
TELEGRAM_TOKEN = "7811297577:AAFDDdcbV7KwDejK04M25ggxYNUqTEEmBvM"
CHAT_ID = "1519003075"

# === Coin listeleri ===
COINS_15M = ["FLOKI_USDT", "SUI_USDT", "ONDO_USDT", "APT_USDT", "STORJ_USDT",
             "TAKE_USDT", "MOVE_USDT", "WLFI_USDT", "INJ_USDT", "WLD_USDT",
             "HYPE_USDT", "BNB_USDT", "TIA_USDT", "PUMPFUN_USDT", "HOLO_USDT",
             "ARB_USDT", "TONCOIN_USDT", "NEAR_USDT", "TAO_USDT", "ETHFI_USDT",
             "SLF_USDT", "MRLN_USDT", "STREAMER_USDT"]
COINS_1H = ["LTC_USDT", "XLM_USDT", "XRP_USDT", "APT_USDT", "TAO_USDT",
            "ONDO_USDT", "DOT_USDT", "NEAR_USDT", "HYPE_USDT", "MANA_USDT",
            "ARB_USDT", "INJ_USDT", "MOVE_USDT", "FLOKI_USDT"]

# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# === Basit strateji: sweep + wick + volume ===
def check_signal(symbol, interval="15m"):
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&limit=50"
    r = requests.get(url)
    data = r.json().get("data", [])
    if len(data) < 3:
        return None
    
    df = pd.DataFrame(data)
    df.columns = ["time","open","close","high","low","vol","amount","realOpen","realClose","realHigh","realLow"]
    df["open"] = df["open"].astype(float)
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["vol"] = df["vol"].astype(float)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # sweep: önceki low kırıldı mı?
    sweep = last["low"] < prev["low"]

    # wick: fitil/gövde oranı
    body = abs(last["close"] - last["open"])
    wick = (last["high"] - last["low"]) > body * 1.5

    # volume: ortalamanın üstünde mi?
    vol_ok = last["vol"] > df["vol"].mean()

    if sweep and wick and vol_ok:
        return f"🟢 LONG sinyal | {symbol} | Fiyat: {last['close']}"
    elif sweep and wick:
        return f"🔴 SHORT sinyal | {symbol} | Fiyat: {last['close']}"
    return None

# === Ana Bot ===
async def run_bot():
    bot = Bot(token=TELEGRAM_TOKEN)

    while True:
        for sym in COINS_15M:
            signal = check_signal(sym, interval="Min15")
            if signal:
                await bot.send_message(chat_id=CHAT_ID, text=f"[15m] {signal}")
                logging.info(f"15m sinyal gönderildi: {signal}")

        for sym in COINS_1H:
            signal = check_signal(sym, interval="Min60")
            if signal:
                await bot.send_message(chat_id=CHAT_ID, text=f"[1h] {signal}")
                logging.info(f"1h sinyal gönderildi: {signal}")

        logging.info("✅ Yeni kontrol tamamlandı.")
        await asyncio.sleep(60)  # 1 dk bekle

if __name__ == "__main__":
    asyncio.run(run_bot())
