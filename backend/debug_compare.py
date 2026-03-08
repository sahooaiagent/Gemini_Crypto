"""
Debug script: Run AMA PRO TEMA on a single symbol and print
detailed indicator values for the last 15 candles so we can
compare with TradingView's AMA_PRO_TEMA indicator output.
"""
import asyncio
import sys
import pandas as pd
import numpy as np

# Reuse the scanner's functions
from scanner import (
    exchange, fetch_binance_data, calculate_adx, calculate_atr,
    calculate_ema, calculate_tema
)

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
TIMEFRAME = sys.argv[2] if len(sys.argv) > 2 else "1hr"
SPEED = sys.argv[3] if len(sys.argv) > 3 else "Medium"
MIN_BARS = int(sys.argv[4]) if len(sys.argv) > 4 else 3


async def debug_run():
    print(f"\n{'='*80}")
    print(f"  DEBUG: {SYMBOL} | TF: {TIMEFRAME} | Speed: {SPEED} | MinBars: {MIN_BARS}")
    print(f"{'='*80}\n")

    df_raw = await fetch_binance_data(SYMBOL, TIMEFRAME, limit=500)
    if df_raw is None or len(df_raw) < 200:
        print("ERROR: Not enough data")
        await exchange.close()
        return

    print(f"Raw candles fetched: {len(df_raw)}")
    print(f"Last raw candle (FORMING): {df_raw.index[-1]}  O={df_raw['open'].iloc[-1]:.2f} H={df_raw['high'].iloc[-1]:.2f} L={df_raw['low'].iloc[-1]:.2f} C={df_raw['close'].iloc[-1]:.2f}")
    print(f"Second-last (CLOSED):      {df_raw.index[-2]}  O={df_raw['open'].iloc[-2]:.2f} H={df_raw['high'].iloc[-2]:.2f} L={df_raw['low'].iloc[-2]:.2f} C={df_raw['close'].iloc[-2]:.2f}")

    # Drop forming candle (matching scanner logic)
    df = df_raw.iloc[:-1].copy()
    print(f"\nAfter dropping forming candle: {len(df)} rows")
    print(f"df[-1] (latest closed): {df.index[-1]}")

    # === PARAMETERS ===
    i_emaFastMin, i_emaFastMax = 8, 21
    i_emaSlowMin, i_emaSlowMax = 21, 55
    i_adxLength = 14
    i_adxThreshold = 25
    i_volLookback = 50
    sensitivity_mult = 1.5 if SPEED == 'High' else 0.5 if SPEED == 'Low' else 1.0

    # === SECTION 3: REGIME ===
    df['ADX'] = calculate_adx(df['high'], df['low'], df['close'], i_adxLength)
    df['ATR'] = calculate_atr(df['high'], df['low'], df['close'], 14)
    df['returns'] = np.log(df['close'] / df['close'].shift(1))
    df['volatility'] = df['returns'].rolling(window=i_volLookback).std(ddof=0) * np.sqrt(252) * 100
    df['hist_vol'] = df['volatility'].rolling(window=i_volLookback).mean()
    df['vol_ratio'] = (df['volatility'] / df['hist_vol'].replace(0, np.nan)).fillna(1.0)

    df['ema20'] = calculate_ema(df['close'], 20)
    df['ema50'] = calculate_ema(df['close'], 50)
    df['ema200'] = calculate_ema(df['close'], 200)

    df['roc10'] = df['close'].pct_change(10) * 100
    df['roc20'] = df['close'].pct_change(20) * 100
    df['momentum'] = (df['roc10'] + df['roc20']) / 2

    df['volRegime'] = np.select(
        [df['vol_ratio'] > 1.3, df['vol_ratio'] < 0.7],
        ['High', 'Low'], default='Normal'
    )
    df['trendRegime'] = np.where(df['ADX'] > i_adxThreshold, 'Trending', 'Ranging')

    trend_up = (df['close'] > df['ema20']) & (df['ema20'] > df['ema50']) & (df['ema50'] > df['ema200'])
    trend_down = (df['close'] < df['ema20']) & (df['ema20'] < df['ema50']) & (df['ema50'] < df['ema200'])
    df['directionRegime'] = np.select([trend_up, trend_down], ['Bullish', 'Bearish'], default='Neutral')

    # Stable regime
    i_regimeStability = 3
    stable_regime = "Neutral-Normal-Ranging"
    regime_counter = 0
    n_rows = len(df)

    stable_bullish = np.zeros(n_rows, dtype=bool)
    stable_bearish = np.zeros(n_rows, dtype=bool)
    stable_high_vol = np.zeros(n_rows, dtype=bool)
    stable_low_vol = np.zeros(n_rows, dtype=bool)
    stable_trending = np.zeros(n_rows, dtype=bool)
    stable_ranging = np.zeros(n_rows, dtype=bool)

    dir_vals = df['directionRegime'].values
    vol_vals = df['volRegime'].values
    trend_vals = df['trendRegime'].values

    for i in range(n_rows):
        current_regime = f"{dir_vals[i]}-{vol_vals[i]}-{trend_vals[i]}"
        if current_regime != stable_regime:
            regime_counter += 1
            if regime_counter >= i_regimeStability:
                stable_regime = current_regime
                regime_counter = 0
        else:
            regime_counter = 0
        stable_bullish[i] = "Bullish" in stable_regime
        stable_bearish[i] = "Bearish" in stable_regime
        stable_high_vol[i] = "High" in stable_regime
        stable_low_vol[i] = "Low" in stable_regime
        stable_trending[i] = "Trending" in stable_regime
        stable_ranging[i] = "Ranging" in stable_regime

    df['regimeIsBullish'] = stable_bullish
    df['regimeIsBearish'] = stable_bearish
    df['regimeIsHighVol'] = stable_high_vol
    df['regimeIsLowVol'] = stable_low_vol
    df['regimeIsTrending'] = stable_trending
    df['regimeIsRanging'] = stable_ranging

    # === SECTION 4: ADAPTIVE PARAMETERS ===
    vol_adjust = np.select(
        [df['regimeIsHighVol'], df['regimeIsLowVol']],
        [0.7, 1.3], default=1.0
    )
    trend_adjust = np.where(df['regimeIsTrending'], 0.8, 1.2)

    tf_clean = TIMEFRAME.lower().strip()
    if 'min' in tf_clean:
        try:
            m = int(tf_clean.replace('min', ''))
            tf_multiplier = 0.8 if m <= 5 else 1.0 if m <= 60 else 1.2
        except: tf_multiplier = 1.0
    elif 'hr' in tf_clean:
        try:
            h = int(tf_clean.replace('hr', ''))
            minutes = h * 60
            tf_multiplier = 1.0 if minutes <= 60 else 1.2
        except: tf_multiplier = 1.0
    elif 'day' in tf_clean:
        tf_multiplier = 1.3
    elif 'week' in tf_clean:
        tf_multiplier = 1.5
    else:
        tf_multiplier = 1.0

    combined_adjust = vol_adjust * trend_adjust * tf_multiplier * sensitivity_mult
    adjust_factor = np.clip(1.0 / combined_adjust, 0.5, 1.5)

    fast_range = i_emaFastMax - i_emaFastMin
    slow_range = i_emaSlowMax - i_emaSlowMin
    adaptive_fast = i_emaFastMin + fast_range * (1 - adjust_factor)
    adaptive_slow = i_emaSlowMin + slow_range * (1 - adjust_factor)
    adaptive_slow = np.maximum(adaptive_slow, adaptive_fast + 6)

    # TEMA
    temas = {p: calculate_tema(df['close'], p) for p in [8, 10, 12, 14, 16, 18, 21, 26, 30, 34, 38, 42, 47, 55]}

    df['temaFast'] = np.select(
        [adaptive_fast <= 9, adaptive_fast <= 11, adaptive_fast <= 13,
         adaptive_fast <= 15, adaptive_fast <= 17, adaptive_fast <= 19],
        [temas[8], temas[10], temas[12], temas[14], temas[16], temas[18]],
        default=temas[21]
    )
    df['temaSlow'] = np.select(
        [adaptive_slow <= 28, adaptive_slow <= 32, adaptive_slow <= 36,
         adaptive_slow <= 40, adaptive_slow <= 44, adaptive_slow <= 51],
        [temas[26], temas[30], temas[34], temas[38], temas[42], temas[47]],
        default=temas[55]
    )

    # === SECTION 5: CROSSOVERS ===
    df['longCondition'] = (df['temaFast'] > df['temaSlow']) & (df['temaFast'].shift(1) <= df['temaSlow'].shift(1))
    df['shortCondition'] = (df['temaFast'] < df['temaSlow']) & (df['temaFast'].shift(1) >= df['temaSlow'].shift(1))

    # === SECTION 6: longValid / shortValid ===
    n = len(df)
    bars_since_long = np.full(n, 999, dtype=int)
    bars_since_short = np.full(n, 999, dtype=int)
    long_valid = np.zeros(n, dtype=bool)
    short_valid = np.zeros(n, dtype=bool)

    long_cond = df['longCondition'].values
    short_cond = df['shortCondition'].values
    is_bullish = df['regimeIsBullish'].values
    is_bearish = df['regimeIsBearish'].values
    momentum_vals = df['momentum'].values

    for i in range(1, n):
        if long_cond[i]:
            bars_since_long[i] = 0
        else:
            bars_since_long[i] = bars_since_long[i - 1] + 1

        if short_cond[i]:
            bars_since_short[i] = 0
        else:
            bars_since_short[i] = bars_since_short[i - 1] + 1

        lv = long_cond[i] and (bars_since_long[i - 1] >= MIN_BARS)
        sv = short_cond[i] and (bars_since_short[i - 1] >= MIN_BARS)

        if lv and sv:
            if is_bullish[i]:
                sv = False
            elif is_bearish[i]:
                lv = False
            else:
                if momentum_vals[i] > 0:
                    sv = False
                else:
                    lv = False

        long_valid[i] = lv
        short_valid[i] = sv

    df['longValid'] = long_valid
    df['shortValid'] = short_valid

    # =========================================================================
    # PRINT DETAILED OUTPUT FOR LAST 20 CANDLES
    # =========================================================================
    print(f"\n{'='*120}")
    print(f"  LAST 20 CANDLES — Compare with TradingView AMA_PRO_TEMA indicator")
    print(f"{'='*120}")

    last_n = 20
    for k in range(last_n, 0, -1):
        idx = -k
        if abs(idx) >= len(df):
            continue
        row = df.iloc[idx]
        ts = df.index[idx]

        # Adaptive periods for this bar
        af = adaptive_fast[df.index.get_loc(ts)] if hasattr(adaptive_fast, '__getitem__') else adaptive_fast
        als = adaptive_slow[df.index.get_loc(ts)] if hasattr(adaptive_slow, '__getitem__') else adaptive_slow

        # Determine which TEMA period was selected
        if isinstance(af, (np.ndarray, pd.Series)):
            af_val = af
        else:
            af_val = af
        if isinstance(als, (np.ndarray, pd.Series)):
            als_val = als
        else:
            als_val = als

        regime_str = f"{'Bull' if row['regimeIsBullish'] else 'Bear' if row['regimeIsBearish'] else 'Neut'}-{'HiV' if row['regimeIsHighVol'] else 'LoV' if row['regimeIsLowVol'] else 'NrV'}-{'Trd' if row['regimeIsTrending'] else 'Rng'}"

        lc = "LC" if row['longCondition'] else "  "
        sc = "SC" if row['shortCondition'] else "  "
        lv = "LV" if row['longValid'] else "  "
        sv = "SV" if row['shortValid'] else "  "
        signal_str = f"{lc} {sc} | {lv} {sv}"

        print(
            f"  [{idx:3d}] {ts} | "
            f"C={row['close']:>10.2f} | "
            f"TEMA_F={row['temaFast']:>10.2f}  TEMA_S={row['temaSlow']:>10.2f} | "
            f"ADX={row['ADX']:>5.1f} VR={row['vol_ratio']:>4.2f} | "
            f"{regime_str:15s} | "
            f"{signal_str}"
        )

    # Print summary of all longValid/shortValid in the last 50 candles
    print(f"\n{'='*80}")
    print(f"  ALL longValid / shortValid SIGNALS in last 50 candles")
    print(f"{'='*80}")
    signal_count = 0
    for k in range(50, 0, -1):
        idx = -k
        if abs(idx) >= len(df):
            continue
        row = df.iloc[idx]
        ts = df.index[idx]
        if row['longValid'] or row['shortValid']:
            sig = "LONG (longValid)" if row['longValid'] else "SHORT (shortValid)"
            print(f"  [{idx:3d}] {ts} | {sig} | C={row['close']:.2f} | TEMA_F={row['temaFast']:.2f} TEMA_S={row['temaSlow']:.2f}")
            signal_count += 1
    if signal_count == 0:
        print("  (none)")

    print(f"\n  Total signals in last 50 candles: {signal_count}")

    # Print what the scanner's 5-candle lookback would return
    print(f"\n{'='*80}")
    print(f"  SCANNER 5-CANDLE LOOKBACK RESULT (what would be reported)")
    print(f"{'='*80}")
    found_signal = None
    for lookback_idx in range(1, 6):
        idx = -lookback_idx
        if abs(idx) >= len(df):
            continue
        row = df.iloc[idx]
        ts = df.index[idx]
        potential = None
        if row['longValid']:
            potential = "LONG"
        elif row['shortValid']:
            potential = "SHORT"
        if potential:
            signal_high = row['high']
            signal_low = row['low']
            candles_after = df.iloc[idx + 1:]
            breach = False
            if potential == "LONG":
                for _, later in candles_after.iterrows():
                    if later['high'] > signal_high:
                        breach = True
                        break
            else:
                for _, later in candles_after.iterrows():
                    if later['low'] < signal_low:
                        breach = True
                        break
            status = "BREACHED — skipped" if breach else "FRESH — reported!"
            print(f"  [{idx:3d}] {ts} | {potential} | {status}")
            if not breach and found_signal is None:
                found_signal = (potential, ts)

    if found_signal:
        print(f"\n  >>> FINAL SIGNAL: {found_signal[0]} from {found_signal[1]}")
    else:
        print(f"\n  >>> FINAL SIGNAL: None")

    await exchange.close()


if __name__ == "__main__":
    asyncio.run(debug_run())
