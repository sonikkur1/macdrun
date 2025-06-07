import os, time, threading
import yfinance as yf
import pandas as pd
from flask import Flask
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SYMBOLS = ["BTC-USD", "ETH-USD", "ALGO-USD", "XLM-USD", "DOT-USD", "SOL-USD"]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def check_macd_alert(symbol):
    try:
        df = yf.download(symbol, period="30d", interval="1h")
        df.dropna(inplace=True)
        df['EMA12'] = df['Close'].ewm(span=12).mean()
        df['EMA26'] = df['Close'].ewm(span=26).mean()
        df['MACD'] = df['EMA12'] - df['EMA26']
        df['Signal'] = df['MACD'].ewm(span=9).mean()

        macd = df['MACD']
        recent = macd[-6:]

        if (recent[-6] < 0 and
            (recent[-6] - recent[-5]) < -0.018 and
            (recent[-5] - recent[-4]) > 0.005 and
            (recent[-4] - recent[-3]) < -0.01 and
            (recent[-2] - recent[-1]) > 0.015):
            send_telegram(f"📈 MACD pattern alert for {symbol}")
    except Exception as e:
        print(f"Error with {symbol}: {e}")

def run_bot():
    while True:
        for symbol in SYMBOLS:
            check_macd_alert(symbol)
        time.sleep(60 * 30)  # every 30 minutes

@app.route("/")
def home():
    return "MACD Alert Service Running"

# Start the background thread
threading.Thread(target=run_bot).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)