import ccxt
import pandas as pd
import numpy as np
import requests
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

symbols = {
    "BTCUSD": "BTC/USDT",
    "LINKUSD": "LINK/USDT",
    "SOLUSD": "SOL/USDT",
    "XMRUSD": "XMR/USDT",
}

exchange = ccxt.binance()

def fetch_ohlcv(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_indicators(df):
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()
    atr = (df['high'] - df['low']).rolling(10).mean()
    hl2 = (df['high'] + df['low']) / 2
    df['supertrend'] = hl2 - 3 * atr
    df['isBullishTrend'] = df['close'] > df['supertrend']
    df['isBearishTrend'] = df['close'] < df['supertrend']
    df['rsi_short'] = df['close'].rolling(2).apply(lambda x: 100 - (100 / (1 + x[-1]/x[0] - 1)), raw=False)
    df['rsiFalling'] = df['rsi_short'] < df['rsi_short'].shift(1)
    df['volMA'] = df['volume'].rolling(20).mean()
    df['highVolume'] = df['volume'] > 1.5 * df['volMA']
    return df

def detect_signals(df):
    signals = []
    macd = df['macd']
    signal = df['signal']
    rsi = df['rsi']
    trend = df['isBearishTrend']
    vwap = df['vwap']
    close = df['close']
    rsiFall = df['rsiFalling']
    highVol = df['highVolume']

    bullState = bearState = 0
    for i in range(5, len(df)):
        entryLong = entryShort = False

        # simplified pattern logic for brevity
        if macd[i] < 0 and macd[i-1] > macd[i]:
            entryLong = trend[i] and close[i] > vwap[i]
        if macd[i] > 0 and macd[i-1] < macd[i]:
            entryShort = trend[i] and close[i] < vwap[i] and rsi[i] > 35 and rsiFall[i] and highVol[i]

        if entryLong:
            signals.append((df['timestamp'][i], 'LONG'))
        if entryShort:
            signals.append((df['timestamp'][i], 'SHORT'))
    return signals

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=data)

def main():
    for name, symbol in symbols.items():
        df = fetch_ohlcv(symbol)
        df = calculate_indicators(df)
        signals = detect_signals(df)
        for timestamp, signal in signals[-1:]:
            send_telegram(f"{signal} signal for {name} at {timestamp}")

if __name__ == "__main__":
    main()
