import os
import asyncio
import logging
import aiohttp
import pandas as pd
from telegram import Bot

# ========================
# ENV & LOGGING
# ========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")        # Railway Variables
CHAT_ID        = os.getenv("CHAT_ID")               # Railway Variables
LOG_LEVEL      = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s"
)

if not TELEGRAM_TOKEN or not CHAT_ID:
    logging.error("❌ TELEGRAM_TOKEN veya CHAT_ID tanımlı değil! Railway → Variables kısmını kontrol et.")
    raise SystemExit(1)

# ========================
# SETTINGS
# ========================
SYMBOLS_15M = [
    "FLOKI_USDT","SUI_USDT","ONDO_USDT","APT_USDT","STORJ_USDT",
    "TAKE_USDT","MOVE_USDT","WLFI_USDT","INJ_USDT","WLD_USDT",
    "HYPE_USDT","BNB_USDT","TIA_USDT","PUMPFUN_USDT","HOLO_USDT",
    "ARB_USDT","TONCOIN_USDT","NEAR_USDT","TAO_USDT","ETHFI_USDT",
    "SLF_USDT","MRLN_USDT","STREAMER_USDT"
]
SYMBOLS_1H = [
    "LTC_USDT","XLM_USDT","XRP_USDT","APT_USDT","TAO_USDT",
    "ONDO_USDT","DOT_USDT","NEAR_USDT","HYPE_USDT","MANA_USDT",
    "ARB_USDT","INJ_USDT","MOVE_USDT","FLOKI_USDT"
]
INTERVALS = {"Min15": SYMBOLS_15M, "Min60": SYMBOLS_1H}

LOOKBACK     = 500
TP           = 0.015   # %1.5
SL           = 0.02    # %2.0
WICK_MULT    = 1.5
VOL_WINDOW   = 20
SWEEP_LOOKBK = 5       # son 4 barın ([-5:-1]) min/max’ına göre sweep

# coin+tf için son gönderilen bar zamanını tut (aynı bar spam yok)
last_signals = {}   # { "COIN_TF": {"direction": "LONG/SHORT", "bar_time": pd.Timestamp} }

# ========================
# DATA: MEXC Kline
# ========================
async def fetch_klines(session: aiohttp.ClientSession, symbol: str, interval: str, limit: int = LOOKBACK) -> pd.DataFrame:
    """
    MEXC futures kline:
    GET /api/v1/contract/kline/{symbol}?interval=Min15&limit=500
    Dönen "data" dizisini DataFrame'e çevirir.
    """
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&limit={limit}"
    try:
        async with session.get(url, timeout=15) as resp:
            js = await resp.json()
    except Exception as e:
        logging.error(f"[{symbol} | {interval}] FETCH_ERROR: {e}")
        return pd.DataFrame()

    if not isinstance(js, dict) or "data" not in js or not js["data"]:
        return pd.DataFrame()

    df = pd.DataFrame(js["data"])
    # Beklenen sırayı güvenceye al (MEXC genelde bu sırayı döndürüyor)
    # time, open, close, high, low, vol, amount, realOpen, realClose, realHigh, realLow
    if df.shape[1] < 6:
        return pd.DataFrame()

    # isimleri sabitle
    cols = ["time","open","close","high","low","vol"]
    df = df.iloc[:, :6]
    df.columns = cols
    # tip dönüşümleri
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    for c in ["open","close","high","low","vol"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open","close","high","low","vol"])
    # strateji kolaylığı için kolon sırası
    return df[["time","open","high","low","close","vol"]]

# ========================
# STRATEGY (sweep + wick + volume)
# ========================
def check_strategy(df: pd.DataFrame, symbol: str, interval: str):
    """
    Bar kapanışında koşulları değerlendirir.
    sweep: son bar önceki aralığın dışına taşıyor mu?
    wick : fitil/gövde oranı
    vol  : vol > rolling mean
    Koşullar sağlanırsa (direction, bar_time, price) döner; değilse None.
    Ayrıca HER COIN için tek satır debug log basar.
    """
    if df.empty or len(df) < max(VOL_WINDOW, SWEEP_LOOKBK + 2):
        logging.info(f"[{symbol} | {interval}] data_yok/az=len:{len(df)}")
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Sweep
    sweep_low  = last["low"]  < df["low"].iloc[-(SWEEP_LOOKBK):-1].min()
    sweep_high = last["high"] > df["high"].iloc[-(SWEEP_LOOKBK):-1].max()
    sweep = sweep_low or sweep_high

    # Wick (fitil/gövde)
    body      = abs(last["close"] - last["open"])
    wick_rng  = (last["high"] - last["low"])
    wick_ok   = wick_rng > (WICK_MULT * body)

    # Volume
    vol_ma = df["vol"].rolling(VOL_WINDOW).mean().iloc[-1]
    vol_ok = last["vol"] > vol_ma if pd.notna(vol_ma) else False

    # direction
    direction = None
    if sweep and wick_ok and vol_ok:
        direction = "LONG" if last["close"] > prev["close"] else "SHORT"

    # Tek satır log (debug)
    logging.info(
        f"[{symbol} | {interval}] bar={pd.to_datetime(last['time']).strftime('%Y-%m-%d %H:%M:%S')} "
        f"sweep(L/H)={int(sweep_low)}/{int(sweep_high)} wick_ok={int(wick_ok)} "
        f"vol_ok={int(vol_ok)} vol={last['vol']:.4f} vol_ma={vol_ma if pd.notna(vol_ma) else float('nan'):.4f} "
        f"close={last['close']:.6f} -> result={direction or 'NONE'}"
    )

    if direction:
        return direction, last["time"], last["close"]
    return None

# ========================
# BOT LOOP
# ========================
async def run_bot():
    bot = Bot(token=TELEGRAM_TOKEN)
    timeout_s = int(os.getenv("LOOP_SEC", "60"))  # kontrol aralığı (sn)

    async with aiohttp.ClientSession() as session:
        while True:
            logging.info("⏳ yeni kontrol başlıyor...")
            for interval, symbols in INTERVALS.items():
                for sym in symbols:
                    df = await fetch_klines(session, sym, interval, LOOKBACK)
                    if df.empty:
                        continue

                    result = check_strategy(df, sym, interval)
                    if not result:
                        continue

                    direction, bar_time, price = result
                    key = f"{sym}_{interval}"

                    # Aynı bar tekrarını engelle → yeni bar kapanınca tekrar düşer (yön fark etmez)
                    if key in last_signals and last_signals[key]["bar_time"] == bar_time:
                        logging.info(f"[{sym} | {interval}] SKIP same_bar (already sent)")
                        continue

                    # KAYDET & GÖNDER
                    last_signals[key] = {"direction": direction, "bar_time": bar_time}
                    msg = (
                        f"[{interval}] {'🟢 LONG' if direction=='LONG' else '🔴 SHORT'} sinyal | {sym}\n"
                        f"💰 Fiyat: {price:.6f}\n"
                        f"🎯 TP: {TP*100:.1f}% | 🛑 SL: {SL*100:.1f}%"
                    )
                    try:
                        await bot.send_message(chat_id=CHAT_ID, text=msg)
                        logging.info(f"[{sym} | {interval}] SENT dir={direction} bar={pd.to_datetime(bar_time).strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        logging.error(f"[{sym} | {interval}] TELEGRAM_ERROR: {e}")

            logging.info("✅ kontrol tamamlandı, bekleniyor...\n")
            await asyncio.sleep(timeout_s)

if __name__ == "__main__":
    asyncio.run(run_bot())
