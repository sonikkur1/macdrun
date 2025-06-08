import pandas as pd
import requests
import time
from ta.trend import MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID'

SYMBOLS = ["BTCUSDT", "LINKUSDT", "SOLUSDT", "XMRUSDT"]
INTERVAL = '15m'
LIMIT = 100

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    requests.post(url, data=payload)

def fetch_ohlcv(symbol, interval='15m', limit=100):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'trades',
        'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df.astype(float)
    return df

def calculate_indicators(df):
    df['macd'] = MACD(df['close']).macd()
    df['macd_signal'] = MACD(df['close']).macd_signal()
    df['rsi'] = RSIIndicator(df['close'], window=14).rsi()
    df['rsi_short'] = RSIIndicator(df['close'], window=5).rsi()
    df['atr'] = AverageTrueRange(df['high'], df['low'], df['close'], window=10).average_true_range()

    # Simple VWAP approximation using cumulative volume and price
    df['cum_vol'] = df['volume'].cumsum()
    df['cum_vol_price'] = (df['close'] * df['volume']).cumsum()
    df['vwap'] = df['cum_vol_price'] / df['cum_vol']

    df['volume_ma'] = df['volume'].rolling(window=20).mean()
    df['high_volume'] = df['volume'] > 1.5 * df['volume_ma']
    df['rsi_falling'] = df['rsi_short'].diff() < 0
    return df

def generate_signals(df):
    signals = {'entry_long': False, 'exit_long': False, 'entry_short': False, 'exit_short': False}

    # Ensure we have enough data
    if len(df) < 6:
        return signals

    macd = df['macd'].values
    macd_signal = df['macd_signal'].values
    rsi = df['rsi'].values
    rsi_falling = df['rsi_falling'].values
    high_volume = df['high_volume'].values
    close = df['close'].values
    vwap = df['vwap'].values
    atr = df['atr'].values
    supertrend = close - atr * 3
    trend_dir = close > supertrend
    is_bullish = trend_dir[-1]
    is_bearish = not trend_dir[-1]

    # === Bullish Pattern ===
    bull_state = 0
    for i in range(-6, 0):
        if macd[i] < 0:
            if bull_state == 0:
                peak = macd[i]
                bull_state = 1
            elif bull_state == 1 and macd[i] < peak - 0.012:
                valley = macd[i]
                bull_state = 2
            elif bull_state == 2 and macd[i] > valley + 0.004:
                temp_rise = macd[i]
                bull_state = 3
            elif bull_state == 3 and macd[i] < temp_rise - 0.007:
                second_valley = macd[i]
                bull_state = 4
            elif bull_state == 4 and macd[i] > second_valley + 0.010 and macd[i] > macd_signal[i] and rsi[i] < 65:
                bull_state = 5
    if bull_state == 5 and is_bullish and close[-1] > vwap[-1]:
        signals['entry_long'] = True

    if signals['entry_long'] and (macd[-1] < macd_signal[-1] or macd[-1] < macd[-2]) and rsi[-1] > 55:
        signals['exit_long'] = True

    # === Bearish Pattern ===
    bear_state = 0
    for i in range(-6, 0):
        if macd[i] > 0:
            if bear_state == 0:
                valley = macd[i]
                bear_state = 1
            elif bear_state == 1 and macd[i] > valley + 0.012:
                peak = macd[i]
                bear_state = 2
            elif bear_state == 2 and macd[i] < peak - 0.004:
                drop = macd[i]
                bear_state = 3
            elif bear_state == 3 and macd[i] > drop + 0.007:
                second_peak = macd[i]
                bear_state = 4
            elif bear_state == 4 and macd[i] < second_peak - 0.010 and macd[i] < macd_signal[i] and rsi[i] > 35:
                bear_state = 5
    if bear_state == 5 and is_bearish and close[-1] < vwap[-1] and rsi[-1] > 35 and rsi_falling[-1] and high_volume[-1]:
        signals['entry_short'] = True

    if signals['entry_short'] and (macd[-1] > macd_signal[-1] or macd[-1] > macd[-2]) and rsi[-1] < 45:
        signals['exit_short'] = True

    return signals

def main():
    for symbol in SYMBOLS:
        try:
            df = fetch_ohlcv(symbol, INTERVAL, LIMIT)
            df = calculate_indicators(df)
            signals = generate_signals(df)

            if signals['entry_long']:
                send_telegram_message(f"📈 LONG Signal for {symbol} (15m)")
            if signals['exit_long']:
                send_telegram_message(f"📉 EXIT LONG Signal for {symbol} (15m)")
            if signals['entry_short']:
                send_telegram_message(f"📉 SHORT Signal for {symbol} (15m)")
            if signals['exit_short']:
                send_telegram_message(f"📈 EXIT SHORT Signal for {symbol} (15m)")
        except Exception as e:
            print(f"Error with {symbol}: {e}")

if __name__ == "__main__":
    main()
