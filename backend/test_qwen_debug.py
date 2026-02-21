"""Debug: Compare Qwen scanner output around 17:15 and 20:15 on ADAUSDT.P @ 45min"""
import asyncio
import logging
import sys
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.WARNING, stream=sys.stdout)

from scanner import (
    fetch_binance_data, calculate_ema, calculate_rsi, calculate_vwap,
    close_exchange
)

def session_vwap(df):
    """VWAP that resets at UTC midnight (matching TradingView ta.vwap for crypto)"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3

    # Detect session boundaries (UTC date changes)
    dates = df.index.date
    vwap = pd.Series(np.nan, index=df.index)

    cum_tp_vol = 0.0
    cum_vol = 0.0
    prev_date = None

    for i in range(len(df)):
        current_date = dates[i]
        if current_date != prev_date:
            # New session — reset
            cum_tp_vol = 0.0
            cum_vol = 0.0
            prev_date = current_date

        cum_tp_vol += typical_price.iloc[i] * df['volume'].iloc[i]
        cum_vol += df['volume'].iloc[i]

        if cum_vol > 0:
            vwap.iloc[i] = cum_tp_vol / cum_vol

    return vwap

async def main():
    symbol = "ADA/USDT:USDT"
    tf = "45min"

    df = await fetch_binance_data(symbol, tf, limit=500)
    await close_exchange()

    if df is None:
        print("ERROR: Failed to fetch data")
        return

    # Drop forming candle
    df = df.iloc[:-1].copy()

    # Timeframe handling
    timeframe_in_minutes = 45  # 45min uses 15min candles resampled
    bars_per_hour = 60 / max(1, timeframe_in_minutes)
    vol_lookback_bars = max(20, round(24 * bars_per_hour))

    print(f"vol_lookback_bars = {vol_lookback_bars}")
    print(f"Total closed candles: {len(df)}")

    # Compute indicators
    df['pctReturn'] = (df['close'] - df['close'].shift(1)) / df['close'].shift(1)
    df['volatility_q'] = df['pctReturn'].rolling(window=vol_lookback_bars, min_periods=1).std()

    shift_bars = min(vol_lookback_bars, len(df) - 1)
    df['priceChange24h'] = df['close'] / df['close'].shift(shift_bars) - 1
    df['priceChange24h'] = df['priceChange24h'].fillna(0)

    df['lowVol'] = (df['volatility_q'] < 0.012) & (df['priceChange24h'].abs() < 0.008)
    df['highVolMomentum'] = (df['volatility_q'] > 0.035) & (df['priceChange24h'] > 0.025)
    df['panicSelling'] = df['priceChange24h'] < -0.03

    df['emaFast12'] = calculate_ema(df['close'], 12)
    df['emaSlow26'] = calculate_ema(df['close'], 26)
    df['rsi'] = calculate_rsi(df['close'], 14)

    # VWAP comparison
    df['vwap_cumulative'] = calculate_vwap(df)  # Our current (WRONG) implementation
    df['vwap_session'] = session_vwap(df)       # Session-resetting (CORRECT)

    # Mode
    modes = []
    for i in range(len(df)):
        if df['lowVol'].iloc[i]:
            modes.append('mean_reversion')
        elif df['highVolMomentum'].iloc[i] or df['panicSelling'].iloc[i]:
            modes.append('trend')
        else:
            modes.append('neutral')
    df['mode'] = modes

    # Show last 15 candles with both VWAPs
    print(f"\n{'='*130}")
    print(f"  ADAUSDT.P @ 45min — Last 15 closed candles")
    print(f"{'='*130}")
    print(f"{'Timestamp':>22} | {'Close':>8} | {'EMA12':>8} | {'EMA26':>8} | {'RSI':>6} | {'VWAP_cum':>10} | {'VWAP_ses':>10} | {'Mode':>15} | {'shortCond_cum':>13} | {'shortCond_ses':>13}")
    print("-" * 130)

    for i in range(-15, 0):
        idx = len(df) + i
        row = df.iloc[idx]
        ts = str(df.index[idx])

        c = row['close']
        ef = row['emaFast12']
        es = row['emaSlow26']
        r = row['rsi']
        vc = row['vwap_cumulative']
        vs = row['vwap_session']
        m = row['mode']

        # shortCondition with cumulative VWAP (current buggy)
        sc_cum = False
        if m == 'neutral' and not pd.isna(vc):
            sc_cum = (c < ef) and (ef < es) and (c < vc)
        elif m == 'mean_reversion' and not pd.isna(r):
            pass  # mean_reversion short needs rsi > 72

        # shortCondition with session VWAP (correct)
        sc_ses = False
        if m == 'neutral' and not pd.isna(vs):
            sc_ses = (c < ef) and (ef < es) and (c < vs)
        elif m == 'mean_reversion' and not pd.isna(r):
            pass

        marker = ""
        if "17:15" in ts:
            marker = " <-- 17:15 (TV signal)"
        elif "20:15" in ts:
            marker = " <-- 20:15 (our signal)"

        print(f"{ts:>22} | {c:>8.4f} | {ef:>8.4f} | {es:>8.4f} | {r:>6.2f} | {vc:>10.4f} | {vs:>10.4f} | {m:>15} | {str(sc_cum):>13} | {str(sc_ses):>13}{marker}")

asyncio.run(main())
