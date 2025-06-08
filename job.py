import os
import ccxt
import pandas as pd
import requests

# === Config ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SYMBOLS = ["BTC/USD", "LINK/USD", "SOL/USD", "XMR/USD"]
TIMEFRAME = '15m'

# === Thresholds ===
DROP_THRESHOLD = 0.012
RISE_TOWARD_ZERO_THRESHOLD = 0.004
SECOND_DROP_THRESHOLD = 0.007
FINAL_RISE_THRESHOLD = 0.010

# === Init ===
kraken = ccxt.kraken({'enableRateLimit': True})
symbol_states = {}

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def compute_indicators(df):
    df['EMA12'] = df['close'].ewm(span=12).mean()
    df['EMA26'] = df['close'].ewm(span=26).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def fetch_data(symbol):
    try:
        ohlcv = kraken.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return compute_indicators(df)
    except Exception as e:
        print(f"Fetch error for {symbol}: {e}")
        return None

def check_pattern(symbol):
    df = fetch_data(symbol)
    if df is None or len(df) < 20:
        return

    macd = df['MACD'].tolist()
    signal = df['Signal'].tolist()
    rsi = df['RSI'].tolist()
    i = -1  # last candle

    if symbol not in symbol_states:
        symbol_states[symbol] = {
            'state': 0, 'peak': None, 'valley': None,
            'tempRise': None, 'secondValley': None,
            'in_trade': False
        }

    s = symbol_states[symbol]
    state = s['state']
    in_trade = s['in_trade']

    if pd.isna(macd[i]) or pd.isna(signal[i]) or pd.isna(rsi[i]):
        return

    # ENTRY Logic
    if macd[i] < 0:
        if state == 0:
            s['peak'] = macd[i]
            state = 1
        elif state == 1 and macd[i] < s['peak'] - DROP_THRESHOLD:
            s['valley'] = macd[i]
            state = 2
        elif state == 2 and macd[i] > s['valley'] + RISE_TOWARD_ZERO_THRESHOLD:
            s['tempRise'] = macd[i]
            state = 3
        elif state == 3 and macd[i] < s['tempRise'] - SECOND_DROP_THRESHOLD:
            s['secondValley'] = macd[i]
            state = 4
        elif (
            state == 4 and
            macd[i] > s['secondValley'] + FINAL_RISE_THRESHOLD and
            macd[i] > signal[i] and
            rsi[i] < 65
        ):
            send_telegram(f"📈 BUY SIGNAL: {symbol} (15m) MACD pattern detected")
            in_trade = True
            state = 5
    else:
        state = 0

    # EXIT Logic
    if in_trade:
        if (macd[i] < signal[i] or macd[i] < macd[i - 1]) and rsi[i] > 55:
            send_telegram(f"📉 EXIT SIGNAL: {symbol} (15m) MACD exit triggered")
            in_trade = False
            state = 0

    # Save state
    symbol_states[symbol] = {
        'state': state,
        'peak': s['peak'],
        'valley': s['valley'],
        'tempRise': s['tempRise'],
        'secondValley': s['secondValley'],
        'in_trade': in_trade
    }

def main():
    for symbol in SYMBOLS:
        check_pattern(symbol)

if __name__ == "__main__":
    main()