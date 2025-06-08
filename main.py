import os
import time
import threading
import pandas as pd
import ccxt
import requests
from flask import Flask

app = Flask(__name__)

# === CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SYMBOLS = ["BTC/USD", "LINK/USD", "SOL/USD", "XMR/USD"]

kraken = ccxt.kraken({'enableRateLimit': True})

# === TELEGRAM ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

# === INDICATORS ===
def compute_indicators(df):
    df['EMA12'] = df['close'].ewm(span=12).mean()
    df['EMA26'] = df['close'].ewm(span=26).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['RSI'] = df['close'].diff().apply(lambda x: max(x, 0)).rolling(14).mean() / \
                df['close'].diff().abs().rolling(14).mean() * 100
    return df

# === FETCH DATA ===
def fetch_ohlcv(symbol):
    try:
        ohlcv = kraken.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return compute_indicators(df)
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

# === MACD PATTERN CHECK ===
symbol_states = {}

def check_macd_pattern(symbol):
    df = fetch_ohlcv(symbol)
    if df is None or len(df) < 20:
        return

    macd = df['MACD'].tolist()
    signal = df['Signal'].tolist()
    rsi = df['RSI'].tolist()
    length = len(macd)

    # Init symbol state if not set
    if symbol not in symbol_states:
        symbol_states[symbol] = {'state': 0, 'peak': None, 'valley': None, 'tempRise': None, 'secondValley': None, 'in_trade': False}

    s = symbol_states[symbol]
    state, peak, valley, tempRise, secondValley, in_trade = s.values()

    # Latest index
    i = length - 1
    if macd[i] >= 0 or any(pd.isna([macd[i], signal[i], rsi[i]])):
        symbol_states[symbol]['state'] = 0
        return

    # ENTRY LOGIC
    if state == 0:
        peak = macd[i]
        state = 1
    elif state == 1 and macd[i] < peak - 0.012:
        valley = macd[i]
        state = 2
    elif state == 2 and macd[i] > valley + 0.004:
        tempRise = macd[i]
        state = 3
    elif state == 3 and macd[i] < tempRise - 0.007:
        secondValley = macd[i]
        state = 4
    elif (
        state == 4 and
        macd[i] > secondValley + 0.010 and
        macd[i] > signal[i] and
        rsi[i] < 65
    ):
        send_telegram(f"📈 BUY SIGNAL: MACD pattern detected on {symbol} (15m)")
        in_trade = True
        state = 5

    # EXIT LOGIC
    if in_trade:
        if (
            macd[i] < signal[i] or
            macd[i] < macd[i - 1] and
            rsi[i] > 55
        ):
            send_telegram(f"📉 EXIT SIGNAL: MACD exit triggered on {symbol} (15m)")
            in_trade = False
            state = 0

    # Save back
    symbol_states[symbol] = {
        'state': state,
        'peak': peak,
        'valley': valley,
        'tempRise': tempRise,
        'secondValley': secondValley,
        'in_trade': in_trade
    }

# === MAIN BOT LOOP ===
def run_bot():
    while True:
        for symbol in SYMBOLS:
            check_macd_pattern(symbol)
        time.sleep(60 * 15)  # every 15 minutes

# === FLASK ROUTE ===
@app.route("/")
def home():
    return "MACD Alert Bot with Entry/Exit (15m) is running."

# === START THREAD ===
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)