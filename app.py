import os
import asyncio
import logging
import aiohttp
import pandas as pd
from datetime import datetime, timezone
from telegram import Bot

# === ENV ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# === SETTINGS ===
SYMBOLS_15M = ["FLOKI_USDT", "SUI_USDT", "ONDO_USDT", "APT_USDT", "STORJ_USDT",
               "TAKE_USDT", "MOVE_USDT", "WLFI_USDT", "INJ_USDT", "WLD_USDT",
               "HYPE_USDT", "BNB_USDT", "TIA_USDT", "PUMPFUN_USDT", "HOLO_USDT",
               "ARB_USDT", "TONCOIN_USDT", "NEAR_USDT", "TAO_USDT", "ETHFI_USDT",
               "SLF_USDT", "MRLN_USDT", "STREAMER_USDT"]

SYMBOLS_1H = ["LTC_USDT", "XLM_USDT", "XRP_USDT", "APT_USDT", "TAO_USDT",
              "ONDO_USDT", "DOT_USDT", "NEAR_USDT", "HYPE_USDT", "MANA_USDT",
              "ARB_USDT", "INJ_USDT", "MOVE_USDT", "FLOKI_USDT"]

INTERVALS = {"15m": SYMBOLS_15M, "1h": SYMBOLS_1H}

LOOKBACK = 500
TP = 0.015   # %1.5
SL = 0.02    # %2.0

logging.basicConfig(level=logging.INFO)


# === FETCH KLINE DATA FROM MEXC ===
async def fetch_klines(session, symbol, interval, limit=LOOKBACK):
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&limit={limit}"
    try:
        async with session.get(url) as resp:
            data = await resp.json()
            if "data" not in data:
                return pd.DataFrame()
            df = pd.DataFrame(data["data"])
            if df.empty:
                return df
            df.columns = ["time", "open", "close", "high", "low", "vol", "amount", "realOpen", "realClose", "realHigh", "realLow"]
            df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
            df = df[["time", "open", "high", "low", "close", "vol"]].astype(float)
            return df
    except Exception as e:
        logging.error(f"Fetch error {symbol}-{interval}: {e}")
        return pd.DataFrame()


# === STRATEGY ===
def check_strategy(df):
    if df.empty or len(df) < 20:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Sweep: son bar önceki dip/tepeyi kırmış mı?
    sweep = last["low"] < df["low"].iloc[-5:-1].min() or last["high"] > df["high"].iloc[-5:-1].max()

    # Wick: fitil/gövde oranı
    body = abs(last["close"] - last["open"])
    wick = (last["high"] - last["low"])
    wick_ok = wick > 1.5 * body

    # Volume filter: son hacim ortalamanın üzerinde mi?
    vol_ok = last["vol"] > df["vol"].rolling(20).mean().iloc[-1]

    if sweep and wick_ok and vol_ok:
        direction = "LONG" if last["close"] > prev["close"] else "SHORT"
        return direction
    return None


# === RUN BOT ===
async def run_bot():
    bot = Bot(token=TELEGRAM_TOKEN)

    async with aiohttp.ClientSession() as session:
        while True:
            logging.info("⏳ Yeni kontrol başlıyor...")
            for interval, symbols in INTERVALS.items():
                for sym in symbols:
                    df = await fetch_klines(session, sym, interval)
                    if df.empty:
                        continue
                    signal = check_strategy(df)
                    if signal:
                        price = df["close"].iloc[-1]
                        msg = f"🟢 SİNYAL | {sym} | {interval}\n➡️ {signal}\n💰 Fiyat: {price:.4f}\n🎯 TP: {TP*100:.1f}% | 🛑 SL: {SL*100:.1f}%"
                        try:
                            await bot.send_message(chat_id=CHAT_ID, text=msg)
                            logging.info(f"Sent: {msg}")
                        except Exception as e:
                            logging.error(f"Telegram send error: {e}")

            logging.info("✅ Kontrol tamamlandı, 60sn bekleniyor...")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(run_bot())
