import ccxt
import pandas as pd
import time
import requests
from ta.trend import MACD
from ta.momentum import RSIIndicator
import os

# === CONFIGURATION ===
symbols = ['BTC/USDT', 'LINK/USDT', 'SOL/USDT', 'XMR/USDT']
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True
    }
})
interval = '15m'
limit = 30  # reduced for lower rate usage
refresh_seconds = 120  # run less frequently to avoid IP bans

# === MACD Pattern Parameters ===
dropThreshold = 0.015
riseTowardZeroThreshold = 0.004
secondDropThreshold = 0.009
finalRiseThreshold = 0.011

# === TELEGRAM CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDs = os.getenv("CHAT_IDs", "")  # comma-separated list
chat_ids = [chat_id.strip() for chat_id in CHAT_IDs.split(',') if chat_id.strip()]

def send_telegram_alert(message):
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                print(f"⚠️ Telegram error for chat_id {chat_id}: {response.text}")
        except Exception as e:
            print(f"⚠️ Failed to send Telegram alert to {chat_id}: {e}")

# === State tracking per symbol ===
symbol_states = {
    s: {
        'long_state': 0,
        'in_trade': False,
        'peak': None,
        'valley': None,
        'temp_rise': None,
        'second_valley': None
    } for s in symbols
}

def fetch_ohlcv(symbol, interval, limit):
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"⚠️ Failed to fetch data for {symbol}: {e}")
        return None

def process_symbol(symbol):
    df = fetch_ohlcv(symbol, interval, limit)
    if df is None or len(df) < 2:
        return

    df.set_index('timestamp', inplace=True)
    macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["rsi"] = RSIIndicator(close=df["close"]).rsi()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    state = symbol_states[symbol]
    long_state = state['long_state']
    in_trade = state['in_trade']

    macd_val = latest["macd"]
    macd_sig = latest["macd_signal"]
    rsi_val = latest["rsi"]
    prev_macd = prev["macd"]
    prev_sig = prev["macd_signal"]

    # === MACD Pattern State Machine ===
    if macd_val < 0:
        if long_state == 0:
            state['peak'] = macd_val
            long_state = 1
        elif long_state == 1 and state['peak'] is not None and macd_val < state['peak'] - dropThreshold:
            state['valley'] = macd_val
            long_state = 2
        elif long_state == 2 and state['valley'] is not None and macd_val > state['valley'] + riseTowardZeroThreshold:
            state['temp_rise'] = macd_val
            long_state = 3
        elif long_state == 3 and state['temp_rise'] is not None and macd_val < state['temp_rise'] - secondDropThreshold:
            state['second_valley'] = macd_val
            long_state = 4
        elif long_state == 4 and state['second_valley'] is not None and \
                macd_val > state['second_valley'] + finalRiseThreshold and \
                rsi_val < 55 and macd_val > macd_sig:
            long_state = 5
    else:
        long_state = 0
        state['peak'] = None
        state['valley'] = None
        state['temp_rise'] = None
        state['second_valley'] = None

    entry_signal = (long_state == 5 or (macd_val > macd_sig and macd_val < 0 and prev_macd < prev_sig)) and not in_trade
    if entry_signal:
        msg = f"📈 [LONG ENTRY] {symbol} at {latest.name.strftime('%Y-%m-%d %H:%M')} | Price: {latest['close']:.2f}"
        print(msg)
        send_telegram_alert(msg)
        in_trade = True

    exit_signal = in_trade and macd_val < macd_sig and macd_val > 0
    if exit_signal:
        msg = f"📉 [LONG EXIT] {symbol} at {latest.name.strftime('%Y-%m-%d %H:%M')} | Price: {latest['close']:.2f}"
        print(msg)
        send_telegram_alert(msg)
        in_trade = False

    state['long_state'] = long_state
    state['in_trade'] = in_trade

# === Main Execution Loop ===
if __name__ == "__main__":
    print("🚀 Starting crypto alert bot...\n")
    while True:
        for symbol in symbols:
            try:
                process_symbol(symbol)
            except Exception as e:
                print(f"❌ Error processing {symbol}: {e}")
        print("⏳ Waiting for next check...\n")
        time.sleep(refresh_seconds)
