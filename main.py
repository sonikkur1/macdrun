import os, time, threading
import ccxt
import pandas as pd
import requests
from flask import Flask

app = Flask(__name__)

# Telegram setup
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Kraken symbols to monitor
SYMBOLS = ["BTC", "LINK", "SOL", "XMR"]

kraken = ccxt.kraken()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_ohlcv(symbol):
    try:
        market = symbol + '/USD'
        candles = kraken.fetch_ohlcv(market, timeframe='15m', limit=100)
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def check_macd_pattern(symbol):
    df = fetch_ohlcv(symbol)
    if df is None or len(df) < 35:
        return

    df["EMA12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["EMA26"] = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    macd = df["MACD"].dropna()
    if len(macd) < 6:
        return

    # Parameters
    dropThreshold = 0.018
    riseTowardZeroThreshold = 0.005
    secondDropThreshold = 0.01
    finalRiseThreshold = 0.013

    recent = macd.iloc[-6:]
    peak, valley, tempRise, secondValley = recent.iloc[0], None, None, None

    if peak < 0:
        if recent.iloc[1] < peak - dropThreshold:
            valley = recent.iloc[1]
            if recent.iloc[2] > valley + riseTowardZeroThreshold:
                tempRise = recent.iloc[2]
                if recent.iloc[3] < tempRise - secondDropThreshold:
                    secondValley = recent.iloc[3]
                    if recent.iloc[5] > secondValley + finalRiseThreshold:
                        send_telegram(f"📈 MACD pattern triggered for {symbol}/USD (15m, Kraken)")

def run_bot():
    while True:
        for symbol in SYMBOLS:
            check_macd_pattern(symbol)
        time.sleep(60 * 15)  # every 15 minutes

@app.route("/")
def home():
    return "Kraken MACD Alert Service Running"

# Start bot in background thread
threading.Thread(target=run_bot).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)