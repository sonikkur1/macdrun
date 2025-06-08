import requests
import pandas as pd
from datetime import datetime, timedelta
from ta.trend import MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

# === Settings ===
SYMBOL = 'BTC/USDT'
INTERVAL = '15m'
LIMIT = 100
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID'

# === Fetch OHLCV data ===
def fetch_ohlcv():
    import ccxt
    exchange = ccxt.binance()
    ohlcv = exchange.fetch_ohlcv(SYMBOL, INTERVAL, limit=LIMIT)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

# === Supertrend ===
def calculate_supertrend(df, period=10, multiplier=3.0):
    atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=period).average_true_range()
    hl2 = (df['high'] + df['low']) / 2
    upperband = hl2 + multiplier * atr
    lowerband = hl2 - multiplier * atr
    supertrend = [False] * len(df)
    direction = [0] * len(df)
    in_uptrend = True

    for i in range(1, len(df)):
        if df['close'].iloc[i] > upperband.iloc[i-1]:
            in_uptrend = True
        elif df['close'].iloc[i] < lowerband.iloc[i-1]:
            in_uptrend = False

        if in_uptrend:
            lowerband.iloc[i] = max(lowerband.iloc[i], lowerband.iloc[i-1])
        else:
            upperband.iloc[i] = min(upperband.iloc[i], upperband.iloc[i-1])

        supertrend[i] = lowerband.iloc[i] if in_uptrend else upperband.iloc[i]
        direction[i] = 1 if in_uptrend else -1

    df['supertrend'] = supertrend
    df['supertrend_dir'] = direction
    return df

# === VWAP ===
def calculate_vwap(df):
    cumulative_vol = df['volume'].cumsum()
    cumulative_tp_vol = (df['close'] * df['volume']).cumsum()
    df['vwap'] = cumulative_tp_vol / cumulative_vol
    return df

# === Alert Function ===
def send_alert(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg}
    requests.post(url, data=payload)

# === Strategy Logic ===
def run():
    df = fetch_ohlcv()
    df = calculate_supertrend(df)
    df = calculate_vwap(df)

    macd = MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['signal'] = macd.macd_signal()
    df['rsi'] = RSIIndicator(close=df['close']).rsi()

    entry_long, exit_long = False, False
    entry_short, exit_short = False, False

    # === Bullish Pattern ===
    bull_state = 0
    for i in range(-10, 0):
        if df['macd'].iloc[i] < 0:
            if bull_state == 0:
                peak = df['macd'].iloc[i]
                bull_state = 1
            elif bull_state == 1 and df['macd'].iloc[i] < peak - 0.012:
                valley = df['macd'].iloc[i]
                bull_state = 2
            elif bull_state == 2 and df['macd'].iloc[i] > valley + 0.004:
                tempRise = df['macd'].iloc[i]
                bull_state = 3
            elif bull_state == 3 and df['macd'].iloc[i] < tempRise - 0.007:
                secondValley = df['macd'].iloc[i]
                bull_state = 4
            elif bull_state == 4 and df['macd'].iloc[i] > secondValley + 0.010 and \
                 df['macd'].iloc[i] > df['signal'].iloc[i] and df['rsi'].iloc[i] < 65 and \
                 df['supertrend_dir'].iloc[i] == 1 and df['close'].iloc[i] > df['vwap'].iloc[i]:
                entry_long = True
        else:
            bull_state = 0

    # === Exit Long ===
    if df['macd'].iloc[-2] > 0 and df['macd'].iloc[-1] < df['signal'].iloc[-1] and df['rsi'].iloc[-1] > 55:
        exit_long = True

    # === Bearish Pattern ===
    bear_state = 0
    for i in range(-10, 0):
        if df['macd'].iloc[i] > 0:
            if bear_state == 0:
                valley = df['macd'].iloc[i]
                bear_state = 1
            elif bear_state == 1 and df['macd'].iloc[i] > valley + 0.012:
                peak = df['macd'].iloc[i]
                bear_state = 2
            elif bear_state == 2 and df['macd'].iloc[i] < peak - 0.004:
                drop = df['macd'].iloc[i]
                bear_state = 3
            elif bear_state == 3 and df['macd'].iloc[i] > drop + 0.007:
                secondPeak = df['macd'].iloc[i]
                bear_state = 4
            elif bear_state == 4 and df['macd'].iloc[i] < secondPeak - 0.010 and \
                 df['macd'].iloc[i] < df['signal'].iloc[i] and df['rsi'].iloc[i] > 35 and \
                 df['supertrend_dir'].iloc[i] == -1 and df['close'].iloc[i] < df['vwap'].iloc[i]:
                entry_short = True
        else:
            bear_state = 0

    # === Exit Short ===
    if df['macd'].iloc[-2] < 0 and df['macd'].iloc[-1] > df['signal'].iloc[-1] and df['rsi'].iloc[-1] < 45:
        exit_short = True

    if entry_long:
        send_alert("📈 LONG Entry - Bullish MACD + Trend + VWAP confirmed")
    elif exit_long:
        send_alert("📉 EXIT LONG - Conditions met")
    elif entry_short:
        send_alert("📉 SHORT Entry - Bearish MACD + Trend + VWAP confirmed")
    elif exit_short:
        send_alert("📈 COVER SHORT - Conditions met")

if __name__ == '__main__':
    run()