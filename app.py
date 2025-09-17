import os
import asyncio
import logging
import aiohttp
import pandas as pd
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

# === Son gönderilen sinyaller (coin+tf+bar_time) ===
last_signals = {}


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

    # Sweep
    sweep = last["low"] < df["low"].iloc[-5:-1].min() or last["high"] > df["high"].iloc[-5:-1].max()
    # Wick
    body = abs(last["close"] - last["open"])
    wick = (last["high"] - last["low"])
    wick_ok = wick > 1.5 * body
    # Volume
    vol_ok = last["vol"] > df["vol"].rolling(20).mean().iloc[-1]

    logging.info(f"Check {df.iloc[-1]['time']} | sweep={sweep}, wick_ok={wick_ok}, vol_ok={vol_ok}")

    if sweep and wick_ok and vol_ok:
        direction = "LONG" if last["close"] > prev["close"] else "SHORT"
        return direction, last["time"], last["close"]
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
                    result = check_strategy(df)
                    if result:
                        direction, bar_time, price = result
                        key = f"{sym}_{interval}"

                        # Aynı bar için tekrar sinyal göndermeyi engelle
                        if key in last_signals and last_signals[key]["bar_time"] == bar_time:
                            logging.info(f"⏩ Skip (aynı bar) {sym} {interval} {direction}")
                            continue

                        # Yeni sinyal → kaydet & gönder
                        last_signals[key] = {"direction": direction, "bar_time": bar_time}

                        msg = f"[{interval}] {'🟢 LONG' if direction=='LONG' else '🔴 SHORT'} sinyal | {sym}\n💰 Fiyat: {price:.4f}\n🎯 TP: {TP*100:.1f}% | 🛑 SL: {SL*100:.1f}%"
                        try:
                            await bot.send_message(chat_id=CHAT_ID, text=msg)
                            logging.info(f"✅ Sent: {sym} {interval} {direction} @ {bar_time}")
                        except Exception as e:
                            logging.error(f"Telegram send error: {e}")

            logging.info("✅ Kontrol tamamlandı, 60sn bekleniyor...\n")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(run_bot())
