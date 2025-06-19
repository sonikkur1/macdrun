import ccxt
import pandas as pd
import numpy as np
import time
import requests
from ta.trend import MACD
from ta.momentum import RSIIndicator
import os

# === CONFIGURATION ===
symbols = ['BTC/USDT', 'LINK/USDT', 'SOL/USDT', 'XMR/USDT']
exchange = ccxt.binance()
interval = '15m'
limit = 100
refresh_seconds = 60

# === MACD Pattern Parameters ===
dropThreshold = 0.015
riseTowardZeroThreshold = 0.004
secondDropThreshold = 0.009
finalRiseThreshold = 0.011

# === TELEGRAM CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"⚠️ Failed to send Telegram alert: {e}")

# === Track state per symbol ===
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

def fetch_ohlcv(symbol, interval, limit=100):
    data = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def process_symbol(symbol):
    df = fetch_ohlcv(symbol, interval, limit)
    df.set_index('timestamp', inplace=True)

    macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["rsi"] = RSIIndicator(close=df["close"]).rsi()

    if len(df) < 2:
        return

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
        elif long_state == 1 and macd_val < state['peak'] - dropThreshold:
            state['valley'] = macd_val
            long_state = 2
        elif long_state == 2 and macd_val > state['valley'] + riseTowardZeroThreshold:
            state['temp_rise'] = macd_val
            long_state = 3
        elif long_state == 3 and macd_val < state['temp_rise'] - secondDropThreshold:
            state['second_valley'] = macd_val
            long_state = 4
        elif long_state == 4 and macd_val > state['second_valley'] + finalRiseThreshold and rsi_val < 55 and macd_val > macd_sig:
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

if __name__ == "__main__":
    print("🚀 Monitoring Binance crypto pairs with MACD pattern alerts to Telegram...\n")
    while True:
        for symbol in symbols:
            try:
                process_symbol(symbol)
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
        print("⏳ Waiting for next check...\n")
        time.sleep(refresh_seconds)