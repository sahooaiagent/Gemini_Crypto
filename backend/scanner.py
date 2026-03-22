"""
Gemini Scanner — AMA PRO TEMA Logic
====================================
Faithful Python port of the AMA_PRO_TEMA Pine Script indicator.
Uses Triple Exponential Moving Averages (TEMA) with adaptive parameters
based on market regime detection.

Signal: Check if longValid or shortValid occurred on the PREVIOUS closed candle.
"""

import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import httpx
import time
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor

# Global symbols cache
_symbols_cache = {
    "data": None,
    "timestamp": 0
}

# Shared thread pool for CPU intensive calculations
executor = ThreadPoolExecutor(max_workers=4)

# Map UI index names to yfinance tickers
TICKER_MAP = {
    "NIFTY": "^NSEI",
    "NIFTY 50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "BANK NIFTY": "^NSEBANK",
    "DOW JONES": "^DJI",
    "NASDAQ": "^IXIC"
}

# =============================================================================
# TECHNICAL INDICATOR FUNCTIONS
# =============================================================================

def calculate_ema(series, length):
    """Standard EMA"""
    return series.ewm(span=length, adjust=False).mean()

def calculate_tema(series, length):
    """
    Triple Exponential Moving Average (TEMA)
    TEMA = 3*EMA1 - 3*EMA2 + EMA3
    Reduces lag compared to standard EMA.
    """
    ema1 = series.ewm(span=length, adjust=False).mean()
    ema2 = ema1.ewm(span=length, adjust=False).mean()
    ema3 = ema2.ewm(span=length, adjust=False).mean()
    return 3 * ema1 - 3 * ema2 + ema3

def calculate_atr(high, low, close, length):
    """Average True Range using RMA (Wilder's smoothing)"""
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, adjust=False).mean()

def calculate_adx(high, low, close, length):
    """ADX matching Pine Script calcADX"""
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/length, adjust=False).mean()
    
    up = high.diff()
    down = -low.diff()
    
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    
    plus_dm_s = pd.Series(plus_dm, index=high.index).ewm(alpha=1/length, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=high.index).ewm(alpha=1/length, adjust=False).mean()
    
    plus_di = 100 * (plus_dm_s / atr.replace(0, np.nan)).fillna(0)
    minus_di = 100 * (minus_dm_s / atr.replace(0, np.nan)).fillna(0)
    
    di_sum = plus_di + minus_di
    di_sum = di_sum.replace(0, 1e-10)
    dx = 100 * abs(plus_di - minus_di) / di_sum
    return dx.ewm(alpha=1/length, adjust=False).mean()

# =============================================================================
# DATA FETCHING (with retry logic for JSONDecodeError)
# =============================================================================

# =============================================================================
# ASYNC BINANCE DATA FETCHING
# =============================================================================

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',   # USDT-Margined Perpetual contracts
    },
})

async def fetch_binance_data(symbol, timeframe, limit=500):
    """
    Fetches OHLCV data from Binance using CCXT (Async).
    """
    tf_map = {
        '5min': '1m',
        '10min': '5m',
        '15min': '15m',
        '20min': '5m',
        '25min': '5m',
        '30min': '30m',
        '45min': '15m',
        '1hr': '1h',
        '2hr': '2h',
        '4hr': '4h',
        '6hr': '6h',
        '8hr': '8h',
        '12hr': '12h',
        '1 day': '1d',
        '2 day': '1d',
        '3 day': '1d',
        '4 day': '1d',
        '5 day': '1d',
        '6 day': '1d',
        '1 week': '1w',
        '1 month': '1M'
    }

    binance_tf = tf_map.get(timeframe, '15m')

    try:
        logging.info(f"Fetching {symbol} from Binance at {timeframe} interval...")
        # Use await for async fetch_ohlcv
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=binance_tf, limit=limit + 50)

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        # Resample for non-standard timeframes
        resample_map = {
            '5min': '5min',
            '10min': '10min',
            '20min': '20min',
            '25min': '25min',
            '45min': '45min',
            '2 day': '2D',
            '3 day': '3D',
            '4 day': '4D',
            '5 day': '5D',
            '6 day': '6D'
        }

        if timeframe in resample_map:
            # For multi-day timeframes, align with TradingView's candle boundaries
            if timeframe in ['2 day', '3 day', '4 day', '5 day', '6 day']:
                # Multi-day candles use origin='epoch' to align with TradingView
                df = df.resample(resample_map[timeframe], origin='epoch').agg({
                    'open': 'first', 'high': 'max',
                    'low': 'min', 'close': 'last',
                    'volume': 'sum'
                }).dropna()
            else:
                # For minute-based timeframes, standard resampling is fine
                df = df.resample(resample_map[timeframe]).agg({
                    'open': 'first', 'high': 'max',
                    'low': 'min', 'close': 'last',
                    'volume': 'sum'
                }).dropna()

        return df.tail(limit)
    except Exception as e:
        logging.error(f"Error fetching Binance data for {symbol}: {str(e)}")
        return None

async def get_top_binance_symbols(limit=100):
    """
    Returns the top N USDT symbols by Market Cap using CoinGecko + Binance Markets.
    Includes caching to prevent rate limits.
    """
    global _symbols_cache
    
    # 1. Check cache (5 minute TTL)
    now = time.time()
    if _symbols_cache["data"] and (now - _symbols_cache["timestamp"] < 300):
        logging.info("Using cached symbols list")
        return _symbols_cache["data"][:limit]

    try:
        logging.info(f"Fetching top {limit} symbols by Market Cap from CoinGecko...")
        
        # 2. Fetch top coins by market cap from CoinGecko
        async with httpx.AsyncClient() as client:
            cg_url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1"
            response = await client.get(cg_url, timeout=10.0)
            cg_data = response.json()
            
        top_names = [coin['symbol'].upper() for coin in cg_data]
        
        # 3. Get available markets and tickers from Binance
        logging.info("Loading Binance markets and tickers...")
        markets = await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
        
        # 4. Match top coins with Binance USDT-Margined Perpetual contracts only
        final_symbols = []
        for coin_sym in top_names:
            perp_symbol = f"{coin_sym}/USDT:USDT"

            if perp_symbol in markets:
                ticker = tickers.get(perp_symbol, {})
                final_symbols.append({
                    'symbol': perp_symbol,
                    'change': ticker.get('percentage', 0),
                    'price': ticker.get('last', None)
                })
        
        # Update cache
        _symbols_cache["data"] = final_symbols
        _symbols_cache["timestamp"] = now
        
        return final_symbols[:limit]
    except Exception as e:
        logging.error(f"Error fetching top symbols: {str(e)}")
        # Fallback to empty or previous cache
        return _symbols_cache["data"][:limit] if _symbols_cache["data"] else []

async def close_exchange():
    await exchange.close()

# =============================================================================
# AMA PRO TEMA LOGIC — Faithful Port of Pine Script
# =============================================================================

def apply_ama_pro_tema(df, tf_input="1 day", use_current_candle=False, **kwargs):
    """
    Applies the full AMA PRO TEMA logic:
    1. Market regime detection (ADX, volatility ratio, EMA alignment)
    2. Adaptive TEMA period calculation (with tfMultiplier)
    3. TEMA crossover signals
    4. Signal filtering: longValid / shortValid (min bars between + regime conflict)
    5. Check the PREVIOUS closed candle (index -2) for a valid signal

    If use_current_candle=True, the forming candle is kept (for "Now" mode).

    Returns: (signal, crossover_angle, tema_gap_pct) or (None, None, None)
    """
    if df is None or len(df) < 200:
        return None, None, None

    if not use_current_candle:
        # Drop the last row (current forming/incomplete candle) so all logic
        # runs exclusively on closed candles. After this, df.iloc[-1] is the
        # latest CLOSED candle.
        df = df.iloc[:-1].copy()

    if len(df) < 200:
        return None, None, None

    try:
        # === PINE SCRIPT PARAMETERS ===
        i_emaFastMin, i_emaFastMax = 8, 21
        i_emaSlowMin, i_emaSlowMax = 21, 55
        i_rsiMin, i_rsiMax = 10, 21
        i_adxLength = 14
        i_adxThreshold = 25
        i_volLookback = 50
        
        # User defined parameters
        i_minBarsBetween = kwargs.get('min_bars_between', 3)
        adaptation_speed = kwargs.get('adaptation_speed', 'Medium')
        
        # Sensitivity multiplier: High=1.5, Medium=1.0, Low=0.5 (as per Pine Script)
        sensitivity_mult = 1.5 if adaptation_speed == 'High' else 0.5 if adaptation_speed == 'Low' else 1.0

        # =================================================================
        # SECTION 3: MARKET REGIME DETECTION
        # =================================================================
        df['ADX'] = calculate_adx(df['high'], df['low'], df['close'], i_adxLength)
        
        # Volatility
        df['ATR'] = calculate_atr(df['high'], df['low'], df['close'], 14)
        df['returns'] = np.log(df['close'] / df['close'].shift(1))
        df['volatility'] = df['returns'].rolling(window=i_volLookback).std(ddof=0) * np.sqrt(252) * 100
        df['hist_vol'] = df['volatility'].rolling(window=i_volLookback).mean()
        df['vol_ratio'] = (df['volatility'] / df['hist_vol'].replace(0, np.nan)).fillna(1.0)
        
        # Trend alignment
        df['ema20'] = calculate_ema(df['close'], 20)
        df['ema50'] = calculate_ema(df['close'], 50)
        df['ema200'] = calculate_ema(df['close'], 200)
        
        # Rate of change for momentum
        df['roc10'] = df['close'].pct_change(10) * 100
        df['roc20'] = df['close'].pct_change(20) * 100
        df['momentum'] = (df['roc10'] + df['roc20']) / 2
        
        # Regime classification
        df['volRegime'] = np.select(
            [df['vol_ratio'] > 1.3, df['vol_ratio'] < 0.7],
            ['High', 'Low'], default='Normal'
        )
        df['trendRegime'] = np.where(df['ADX'] > i_adxThreshold, 'Trending', 'Ranging')
        
        trend_up = (df['close'] > df['ema20']) & (df['ema20'] > df['ema50']) & (df['ema50'] > df['ema200'])
        trend_down = (df['close'] < df['ema20']) & (df['ema20'] < df['ema50']) & (df['ema50'] < df['ema200'])
        df['trendAlignment'] = np.select([trend_up, trend_down], [1, -1], default=0)
        df['directionRegime'] = np.select([trend_up, trend_down], ['Bullish', 'Bearish'], default='Neutral')
        
        # Stable regime with confirmation counter (matching Pine Script exactly)
        # The regime only switches after i_regimeStability (3) consecutive bars
        # of a new regime, preventing noisy flip-flopping.
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
                    regime_counter = 0  # Pine Script inner else: reset if not yet stable
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
        
        # =================================================================
        # SECTION 4: ADAPTIVE PARAMETERS — TEMA VERSION
        # =================================================================
        vol_adjust = np.select(
            [df['regimeIsHighVol'], df['regimeIsLowVol']],
            [0.7, 1.3], default=1.0
        )
        trend_adjust = np.where(df['regimeIsTrending'], 0.8, 1.2)
        # tfMultiplier logic from Pine Script:
        # intraday (<=5m: 0.8, <=60m: 1.0, else 1.2)
        # daily: 1.3, weekly/monthly: 1.5
        # tfMultiplier matching Pine Script:
        # timeframe.isintraday: multiplier<=5 → 0.8, <=60 → 1.0, >60 → 1.2
        # timeframe.isdaily: 1.3, weekly+: 1.5
        tf_clean = tf_input.lower().strip()
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
        rsi_range = i_rsiMax - i_rsiMin

        adaptive_fast = i_emaFastMin + fast_range * (1 - adjust_factor)
        adaptive_slow = i_emaSlowMin + slow_range * (1 - adjust_factor)

        # Ensure minimum separation of 6 (TEMA needs slightly larger)
        adaptive_slow = np.maximum(adaptive_slow, adaptive_fast + 6)

        # Adaptive RSI period (matching Pine Script logic)
        rsi_trend_factor = np.where(df['regimeIsTrending'], 0.7, 1.3)
        rsi_vol_factor = np.where(df['regimeIsHighVol'], 0.8, 1.2)
        adaptive_rsi = i_rsiMin + rsi_range * rsi_trend_factor * rsi_vol_factor * sensitivity_mult
        adaptive_rsi = np.clip(adaptive_rsi, i_rsiMin, i_rsiMax)

        # =================================================================
        # PRE-CALCULATE TEMA VALUES (expanded: 50+ lengths)
        # =================================================================
        tema_periods = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                        21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 32, 34, 36, 38, 40, 42, 44,
                        46, 48, 50, 52, 54, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]
        temas = {p: calculate_tema(df['close'], p) for p in tema_periods}

        # PRE-CALCULATE RSI VALUES (expanded: 25+ lengths)
        rsi_periods = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
                       22, 23, 24, 25, 26, 27, 28, 29, 30, 35]
        rsis = {p: calculate_rsi(df['close'], p) for p in rsi_periods}

        # SELECT TEMA Fast (periods 3–30, integer thresholds matching Pine Script)
        fast_conds = [adaptive_fast <= p for p in range(3, 31)]
        fast_vals = [temas[p] for p in range(3, 31)]
        df['temaFast'] = np.select(fast_conds, fast_vals, default=temas[30])

        # SELECT TEMA Slow (periods 20–100, 2-unit steps matching Pine Script)
        slow_steps = [20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 55, 60, 65, 70, 75, 80, 85, 90, 95]
        slow_conds = [adaptive_slow <= p for p in slow_steps]
        slow_vals = [temas[p] for p in slow_steps]
        df['temaSlow'] = np.select(slow_conds, slow_vals, default=temas[100])

        # SELECT RSI (periods 7–35, integer thresholds matching Pine Script)
        rsi_conds = [adaptive_rsi <= p for p in range(7, 31)] + [adaptive_rsi <= 35]
        rsi_vals_sel = [rsis[p] for p in range(7, 31)] + [rsis[35]]
        df['rsi'] = np.select(rsi_conds, rsi_vals_sel, default=rsis[35])
        
        # =================================================================
        # SECTION 5: STRATEGY LOGIC — TEMA crossovers
        # =================================================================
        df['longCondition'] = (df['temaFast'] > df['temaSlow']) & (df['temaFast'].shift(1) <= df['temaSlow'].shift(1))
        df['shortCondition'] = (df['temaFast'] < df['temaSlow']) & (df['temaFast'].shift(1) >= df['temaSlow'].shift(1))

        # Angle Threshold Filter
        angle_lookback = 3
        fast_slope = (df['temaFast'] - df['temaFast'].shift(angle_lookback)) / angle_lookback
        slow_slope = (df['temaSlow'] - df['temaSlow'].shift(angle_lookback)) / angle_lookback
        slope_diff = fast_slope - slow_slope
        df['crossAngle'] = np.abs(np.degrees(np.arctan(slope_diff * 100)))

        # Determine timeframe-adaptive angle threshold
        tf_clean_angle = tf_input.lower().strip()
        if 'min' in tf_clean_angle:
            try:
                tf_minutes = int(tf_clean_angle.replace('min', ''))
            except:
                tf_minutes = 15
        elif 'hr' in tf_clean_angle:
            try:
                tf_minutes = int(tf_clean_angle.replace('hr', '')) * 60
            except:
                tf_minutes = 60
        elif 'day' in tf_clean_angle:
            tf_minutes = 1440
        else:
            tf_minutes = 15

        angle_threshold = 3.0 if tf_minutes <= 15 else 5.0 if tf_minutes <= 30 else 10.0
        angle_pass = df['crossAngle'] >= angle_threshold
        df['longCondition'] = df['longCondition'] & angle_pass
        df['shortCondition'] = df['shortCondition'] & angle_pass

        # =================================================================
        # SECTION 6: SIGNAL FILTERING — longValid / shortValid
        # =================================================================
        # Track bars since last long/short condition (iterative, matching Pine Script)
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
                bars_since_long[i] = bars_since_long[i-1] + 1
            
            if short_cond[i]:
                bars_since_short[i] = 0
            else:
                bars_since_short[i] = bars_since_short[i-1] + 1
            
            # longValid = longCondition AND barsSinceLastLong >= minBarsBetween
            lv = long_cond[i] and (bars_since_long[i-1] >= i_minBarsBetween if i > 0 else True)
            sv = short_cond[i] and (bars_since_short[i-1] >= i_minBarsBetween if i > 0 else True)
            
            # Resolve conflicts: if both long and short are valid on same bar
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
        
        # =================================================================
        # DEBUG: Log the state of last 10 candles
        # =================================================================
        logging.info("--- Signal check on last 10 candles ---")
        for k in range(10, 0, -1):
            idx_k = -k
            if abs(idx_k) < len(df):
                row = df.iloc[idx_k]
                ts = df.index[idx_k] if hasattr(df.index[idx_k], 'strftime') else str(df.index[idx_k])
                logging.info(
                    f"  Candle[{idx_k}] {ts} | "
                    f"Close={row['close']:.2f} | "
                    f"TEMA_F={row['temaFast']:.2f} TEMA_S={row['temaSlow']:.2f} | "
                    f"longCond={row['longCondition']} shortCond={row['shortCondition']} | "
                    f"longValid={row['longValid']} shortValid={row['shortValid']}"
                )
        
        # =================================================================
        # BUY/SELL ENTRY SIGNAL DETECTION (matching TradingView indicator)
        # =================================================================
        # Track pending signals and entry triggers (like the Pine Script)
        n = len(df)
        pending_buy = np.zeros(n, dtype=bool)
        pending_sell = np.zeros(n, dtype=bool)
        buy_entry = np.zeros(n, dtype=bool)
        sell_entry = np.zeros(n, dtype=bool)
        pending_buy_high = np.full(n, np.nan)
        pending_sell_low = np.full(n, np.nan)

        long_cond = df['longCondition'].values
        short_cond = df['shortCondition'].values
        close_vals = df['close'].values
        high_vals = df['high'].values
        low_vals = df['low'].values

        # Track current pending state
        current_pending_buy = False
        current_pending_sell = False
        current_buy_high = np.nan
        current_sell_low = np.nan

        for i in range(1, n):
            # New crossover signal creates a pending entry
            if long_cond[i]:
                current_pending_buy = True
                current_buy_high = close_vals[i]
                current_pending_sell = False  # Clear opposite pending

            if short_cond[i]:
                current_pending_sell = True
                current_sell_low = close_vals[i]
                current_pending_buy = False  # Clear opposite pending

            # Check for BUY entry: price breaks above pending buy high
            if current_pending_buy and not np.isnan(current_buy_high):
                if close_vals[i] > current_buy_high:
                    buy_entry[i] = True
                    current_pending_buy = False  # Entry triggered, clear pending

            # Check for SELL entry: price breaks below pending sell low
            if current_pending_sell and not np.isnan(current_sell_low):
                if close_vals[i] < current_sell_low:
                    sell_entry[i] = True
                    current_pending_sell = False  # Entry triggered, clear pending

            # Store pending state
            pending_buy[i] = current_pending_buy
            pending_sell[i] = current_pending_sell
            pending_buy_high[i] = current_buy_high
            pending_sell_low[i] = current_sell_low

        df['buyEntry'] = buy_entry
        df['sellEntry'] = sell_entry
        df['pendingBuy'] = pending_buy
        df['pendingSell'] = pending_sell

        # =================================================================
        # SIGNAL CHECK — LATEST CLOSED CANDLE ONLY
        # =================================================================
        # The forming candle was already dropped before processing, so
        # df.iloc[-1] is the latest CLOSED candle.  Only report a signal
        # if longValid or shortValid fired on this candle — stale signals
        # from older candles are not actionable.

        signal = None
        crossover_angle = None
        tema_gap_pct = None
        signal_type = None  # 'CROSSOVER' or 'ENTRY'

        last_row = df.iloc[-1]
        last_ts = df.index[-1]

        # Priority 1: Check for BUY/SELL ENTRY signals
        if last_row['buyEntry']:
            signal = "LONG"
            signal_type = "ENTRY"
        elif last_row['sellEntry']:
            signal = "SHORT"
            signal_type = "ENTRY"
        # Priority 2: Check for crossover signals (only if no entry signal)
        elif last_row['longValid']:
            signal = "LONG"
            signal_type = "CROSSOVER"
        elif last_row['shortValid']:
            signal = "SHORT"
            signal_type = "CROSSOVER"

        if signal:
            logging.info(f"  >>> {signal} {signal_type} signal on latest closed candle {last_ts}")

            # Calculate TEMA gap percentage
            fast_val = last_row['temaFast']
            slow_val = last_row['temaSlow']
            if slow_val != 0:
                tema_gap_pct = round((fast_val - slow_val) / slow_val * 100, 3)

            # Crossover angle (already computed vectorized above)
            crossover_angle = round(float(last_row['crossAngle']), 2) if not np.isnan(last_row['crossAngle']) else 0.0

            # Capture RSI value at signal time
            rsi_value = round(float(last_row['rsi']), 2) if 'rsi' in last_row and not np.isnan(last_row['rsi']) else None

            # Capture Open and Close values at signal time
            open_value = round(float(last_row['open']), 8) if 'open' in last_row and not np.isnan(last_row['open']) else None
            close_value = round(float(last_row['close']), 8) if 'close' in last_row and not np.isnan(last_row['close']) else None
        else:
            logging.info(f"  No signal on latest closed candle {last_ts}.")
            rsi_value = None
            open_value = None
            close_value = None
            signal_type = None

        return signal, crossover_angle, tema_gap_pct, rsi_value, open_value, close_value, signal_type
        
    except Exception as e:
        logging.error(f"Error in AMA PRO TEMA calculation: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return None, None, None, None, None, None, None

# =============================================================================
# MA QWEN LOGIC — Faithful Port of Pine Script
# =============================================================================

def calculate_rsi(series, length=14):
    """RSI matching Pine Script ta.rsi"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def calculate_vwap(df):
    """
    Session VWAP matching TradingView ta.vwap for crypto.
    Resets at UTC midnight (00:00) each day.
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    dates = df.index.date
    vwap = pd.Series(np.nan, index=df.index)

    cum_tp_vol = 0.0
    cum_vol = 0.0
    prev_date = None

    for i in range(len(df)):
        current_date = dates[i]
        if current_date != prev_date:
            cum_tp_vol = 0.0
            cum_vol = 0.0
            prev_date = current_date

        cum_tp_vol += typical_price.iloc[i] * df['volume'].iloc[i]
        cum_vol += df['volume'].iloc[i]

        if cum_vol > 0:
            vwap.iloc[i] = cum_tp_vol / cum_vol

    return vwap

# =============================================================================
# HILEGA-ALMA INDICATOR FUNCTIONS
# =============================================================================

def calculate_alma(series, length=9, offset=0.85, sigma=6):
    """
    Arnaud Legoux Moving Average (ALMA)
    Exact implementation matching TradingView's ta.alma

    offset: Gaussian applied to offset (0=gaussian filter, 1=most recent)
    sigma: Defines the sharpness of the gaussian curve

    Formula:
    m = offset * (length - 1)
    s = length / sigma
    wtd = exp(-1 * pow(i - m, 2) / (2 * pow(s, 2)))
    sum = Σ(price[i] * wtd[i]) / Σ(wtd[i])
    """
    values = series.values
    m = offset * (length - 1)
    s = length / sigma

    result = np.full(len(values), np.nan)

    # Pre-calculate weights (they're the same for every window)
    weights = np.array([np.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(length)])

    for i in range(length - 1, len(values)):
        window = values[i - length + 1:i + 1]

        # Handle NaN values
        valid_mask = ~np.isnan(window)
        if np.any(valid_mask):
            valid_weights = weights[valid_mask]
            valid_values = window[valid_mask]
            result[i] = np.sum(valid_values * valid_weights) / np.sum(valid_weights)

    return pd.Series(result, index=series.index)

def calculate_true_rsi_alma(close, length=11):
    """
    True RSI using ALMA smoothing (HILEGA-ALMA version).
    This version is more responsive but differs from standard RSI.

    Pine Script reference:
    delta = src - src[1]
    up := delta > 0 ? delta : 0
    down := delta < 0 ? -delta : 0
    maUp = ta.alma(up, length)
    maDown = ta.alma(down, length)
    """
    delta = close.diff()

    # Separate gains and losses (matching Pine Script exactly)
    up = pd.Series(np.where(delta > 0, delta, 0), index=close.index)
    down = pd.Series(np.where(delta < 0, -delta, 0), index=close.index)

    # Apply ALMA smoothing (offset=0.85, sigma=5 as per the Pine Script)
    ma_up = calculate_alma(up, length=length, offset=0.85, sigma=5)
    ma_down = calculate_alma(down, length=length, offset=0.85, sigma=5)

    # Calculate RS and RSI (matching Pine Script: 100 - (100 / (1 + rs)))
    rs = ma_up / ma_down
    rs = rs.replace([np.inf], np.nan)
    true_rsi = 100 - (100 / (1 + rs))

    # Fill NaN values with 50 (neutral RSI)
    true_rsi = true_rsi.fillna(50)

    return true_rsi

def calculate_true_rsi(close, length=11):
    """
    True RSI using RMA smoothing (HILEGA-ADAPTIVE version).
    This matches TradingView's standard RSI calculation exactly.

    Pine Script reference (Hilega-Adaptive.txt):
    TrueRSI(src, length) =>
        delta = src - src[1]
        up := delta > 0 ? delta : 0
        down := delta < 0 ? -delta : 0
        maUp = ta.rma(up, length)
        maDown = ta.rma(down, length)
        rs = maUp / maDown
        100 - (100 / (1 + rs))

    RMA = Wilder's smoothing = EMA with alpha = 1/length
    """
    delta = close.diff()

    # Separate gains and losses (matching Pine Script exactly)
    gain = pd.Series(np.where(delta > 0, delta, 0), index=close.index)
    loss = pd.Series(np.where(delta < 0, -delta, 0), index=close.index)

    # Apply RMA smoothing (Wilder's smoothing method)
    # RMA is equivalent to EMA with alpha = 1/length
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()

    # Calculate RS and RSI (matching Pine Script: 100 - (100 / (1 + rs)))
    rs = avg_gain / avg_loss.replace(0, np.nan)
    true_rsi = 100 - (100 / (1 + rs))

    # Fill NaN values with 50 (neutral RSI)
    true_rsi = true_rsi.fillna(50)

    return true_rsi

def calculate_vwma(series, volume, length=21):
    """
    Volume Weighted Moving Average
    VWMA = sum(close * volume) / sum(volume) over the period
    Used for smoothing the True RSI
    """
    if volume is None:
        # Fallback to SMA if no volume data available
        return series.rolling(window=length).mean()

    # Calculate VWMA: sum(value * volume) / sum(volume)
    result = (series * volume).rolling(window=length).sum() / volume.rolling(window=length).sum()
    return result

def calculate_tema_of_series(series, length=10):
    """
    Triple Exponential Moving Average applied to a series (like RSI)
    TEMA = 3*EMA1 - 3*EMA2 + EMA3
    """
    ema1 = series.ewm(span=length, adjust=False).mean()
    ema2 = ema1.ewm(span=length, adjust=False).mean()
    ema3 = ema2.ewm(span=length, adjust=False).mean()
    return 3 * ema1 - 3 * ema2 + ema3

def apply_adaptive_htf_cross_scanner(df, scanner_mode='cross_up', tf_input='15min'):
    """
    HILEGA Adaptive HTF Cross Scanner
    Detects RSI crossovers with VWMA using auto-adaptive parameters based on timeframe.

    Based on "Hilega-Adaptive HTF.txt" Pine Script indicator.

    Parameters:
    - df: DataFrame with OHLCV data
    - scanner_mode: 'cross_up' or 'cross_down'
    - tf_input: Timeframe string (e.g., '1min', '15min', '1hr', '1 day')

    Returns:
    - signal: 'LONG' or 'SHORT' or None
    - angle: Percentage difference between RSI and VWMA (as angle proxy)
    - rsi_vwma_diff: Difference (RSI - VWMA)
    - rsi: Current RSI value
    - vwma: Current VWMA value
    - alma: Current ALMA value
    """
    if len(df) < 100:
        return None, None, None, None, None, None

    # Don't drop the last row - we want to detect crossovers on both confirmed and forming candles
    close = df['close']
    volume = df['volume'] if 'volume' in df.columns else None

    # =================================================================
    # HIGHER TIMEFRAME ADAPTATION
    # =================================================================
    # Calculate current timeframe in minutes
    tf_clean = tf_input.lower().strip()
    if 'min' in tf_clean:
        try:
            tf_minutes = int(tf_clean.replace('min', ''))
        except:
            tf_minutes = 15
    elif 'hr' in tf_clean:
        try:
            tf_minutes = int(tf_clean.replace('hr', '')) * 60
        except:
            tf_minutes = 60
    elif 'day' in tf_clean:
        try:
            tf_minutes = int(tf_clean.replace(' day', '').replace('day', '')) * 1440
        except:
            tf_minutes = 1440
    elif 'week' in tf_clean:
        tf_minutes = 10080  # 7 days
    elif 'month' in tf_clean:
        tf_minutes = 43200  # 30 days
    else:
        tf_minutes = 15

    # Determine higher timeframe (matching Pine Script logic)
    if tf_minutes <= 20:
        higher_tf_minutes = 60  # 1H
    elif tf_minutes <= 30:
        higher_tf_minutes = 1440  # 1D
    elif tf_minutes <= 240:
        higher_tf_minutes = 10080  # 1W
    elif tf_minutes <= 2880:
        higher_tf_minutes = 43200  # 1M
    else:
        higher_tf_minutes = 129600  # 3M

    # Adaptation multiplier: Medium sensitivity = 1.0 (hardcoded as per requirement)
    adapt_mult = 1.0

    # Calculate adaptive lengths using logarithmic scaling (matching Pine Script)
    rsi_len = int(np.clip(
        np.round(9 + np.log10(higher_tf_minutes + 1) * 7 * adapt_mult),
        7, 35
    ))

    vwma_len = int(np.clip(
        np.round(16 + np.log10(higher_tf_minutes + 1) * 9 * adapt_mult),
        14, 50
    ))

    alma_len = int(np.clip(
        np.round(8 + np.log10(higher_tf_minutes + 1) * 6 * adapt_mult),
        6, 100
    ))

    logging.info(f"  Adaptive HTF Cross | TF={tf_input} ({tf_minutes}min) → HTF={higher_tf_minutes}min | RSI={rsi_len} | VWMA={vwma_len} | ALMA={alma_len}")

    # =================================================================
    # PRE-COMPUTE RSI VALUES (24 lengths from the script)
    # =================================================================
    rsi_lengths = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 24, 26, 28, 30, 35]
    rsis = {}
    for length in rsi_lengths:
        rsis[length] = calculate_true_rsi(close, length=length)

    # SELECT RSI based on rsi_len (matching Pine Script getRSI function)
    rsi_conditions = [rsi_len <= length for length in rsi_lengths]
    rsi_values = [rsis[length] for length in rsi_lengths]
    true_rsi = np.select(rsi_conditions, rsi_values, default=rsis[35])
    true_rsi = pd.Series(true_rsi, index=close.index)

    # =================================================================
    # VWMA AND ALMA CALCULATIONS
    # =================================================================
    vwma_rsi = calculate_vwma(true_rsi, volume, length=vwma_len)

    # ALMA with fixed parameters (offset=0.85, sigma=6.0 as per script)
    alma_rsi = calculate_alma(true_rsi, length=alma_len, offset=0.85, sigma=6.0)

    # =================================================================
    # CROSSOVER DETECTION
    # =================================================================
    # Check BOTH confirmed candle (index -2) and forming candle (index -1)
    # crossover: rsi[i] > vwma[i] AND rsi[i-1] <= vwma[i-1]
    # crossunder: rsi[i] < vwma[i] AND rsi[i-1] >= vwma[i-1]

    if len(true_rsi) < 3 or len(vwma_rsi) < 3:
        return None, None, None, None, None, None, None

    # Get values for forming candle (index -1)
    forming_rsi = true_rsi.iloc[-1]
    forming_vwma = vwma_rsi.iloc[-1]
    forming_alma = alma_rsi.iloc[-1]

    # Get values for confirmed candle (index -2)
    confirmed_rsi = true_rsi.iloc[-2]
    confirmed_vwma = vwma_rsi.iloc[-2]
    confirmed_alma = alma_rsi.iloc[-2]

    # Get previous values for crossover detection
    prev_confirmed_rsi = true_rsi.iloc[-3]
    prev_confirmed_vwma = vwma_rsi.iloc[-3]
    prev_forming_rsi = true_rsi.iloc[-2]
    prev_forming_vwma = vwma_rsi.iloc[-2]

    # Detect crossover on CONFIRMED candle (previous closed candle)
    confirmed_cross_up = (confirmed_rsi > confirmed_vwma) and (prev_confirmed_rsi <= prev_confirmed_vwma)
    confirmed_cross_down = (confirmed_rsi < confirmed_vwma) and (prev_confirmed_rsi >= prev_confirmed_vwma)

    # Detect crossover on FORMING candle (current candle)
    forming_cross_up = (forming_rsi > forming_vwma) and (prev_forming_rsi <= prev_forming_vwma)
    forming_cross_down = (forming_rsi < forming_vwma) and (prev_forming_rsi >= prev_forming_vwma)

    signal = None
    candle_status = None
    use_rsi = None
    use_vwma = None
    use_alma = None

    # Priority: Confirmed candle first, then forming candle
    if scanner_mode == 'cross_up':
        if confirmed_cross_up and not pd.isna(confirmed_rsi) and not pd.isna(confirmed_vwma):
            signal = 'LONG'
            candle_status = 'Confirmed'
            use_rsi = confirmed_rsi
            use_vwma = confirmed_vwma
            use_alma = confirmed_alma
        elif forming_cross_up and not pd.isna(forming_rsi) and not pd.isna(forming_vwma):
            signal = 'LONG'
            candle_status = 'Forming'
            use_rsi = forming_rsi
            use_vwma = forming_vwma
            use_alma = forming_alma
    elif scanner_mode == 'cross_down':
        if confirmed_cross_down and not pd.isna(confirmed_rsi) and not pd.isna(confirmed_vwma):
            signal = 'SHORT'
            candle_status = 'Confirmed'
            use_rsi = confirmed_rsi
            use_vwma = confirmed_vwma
            use_alma = confirmed_alma
        elif forming_cross_down and not pd.isna(forming_rsi) and not pd.isna(forming_vwma):
            signal = 'SHORT'
            candle_status = 'Forming'
            use_rsi = forming_rsi
            use_vwma = forming_vwma
            use_alma = forming_alma

    if not signal:
        return None, None, None, None, None, None, None

    # =================================================================
    # CALCULATE ANGLE (as percentage difference)
    # =================================================================
    # Angle = ((RSI - VWMA) / VWMA) * 100
    if use_vwma != 0:
        angle = ((use_rsi - use_vwma) / use_vwma) * 100
    else:
        angle = 0.0

    # RSI-VWMA difference
    rsi_vwma_diff = use_rsi - use_vwma

    logging.info(f"  >>> Adaptive HTF Cross {signal} signal ({candle_status}) | RSI={use_rsi:.2f} VWMA={use_vwma:.2f} ALMA={use_alma:.2f} | Angle={angle:.2f}%")

    return signal, angle, rsi_vwma_diff, use_rsi, use_vwma, use_alma, candle_status

def apply_hilega_scanner(df, scanner_mode='buy', rsi_threshold=None, tf_input='15min',
                         rsi_mode='ALMA Fixed', fixed_rsi_length=11, fixed_vwma_length=21, fixed_tema_length=10):
    """
    HILEGA Scanner with Multiple RSI Calculation Modes

    Parameters:
    - df: DataFrame with OHLCV data
    - scanner_mode: 'buy' or 'sell'
    - rsi_threshold: Custom RSI threshold value (default: 10 for buy, 90 for sell)
    - tf_input: Timeframe string (e.g., '15min', '1hr', '1 day') for adaptive length calculation
    - rsi_mode: 'ALMA Fixed', 'ALMA', or 'RMA'
    - fixed_rsi_length: RSI length for ALMA Fixed mode (default: 11)
    - fixed_vwma_length: VWMA length for ALMA Fixed mode (default: 21)
    - fixed_tema_length: TEMA length for ALMA Fixed mode (default: 10)

    Returns:
    - signal: 'LONG' or 'SHORT' or None
    - angle: Angle between True RSI and TEMA
    - rsi_tema_gap: Gap between True RSI and TEMA (True RSI - TEMA)
    - true_rsi: Current True RSI value
    - vwma_rsx: Current VWMA value
    """
    if len(df) < 100:
        return None, None, None, None, None

    # IMPORTANT: For HILEGA scanner, we need to show the FORMING candle RSI
    # This matches TradingView's behavior where the indicator shows real-time
    # values for the current forming candle.
    #
    # User confirmed they want to see the forming candle RSI value (e.g., 84.247)
    # not the last completed candle RSI value (e.g., 75.133)
    #
    # Therefore, we DO NOT drop the last row - we use ALL available data
    # including the forming candle.

    if len(df) < 100:
        return None, None, None, None, None

    close = df['close']
    volume = df['volume'] if 'volume' in df.columns else None

    # =================================================================
    # ADAPTIVE LENGTH CALCULATION BASED ON TIMEFRAME
    # =================================================================
    # Calculate timeframe in minutes
    tf_clean = tf_input.lower().strip()
    if 'min' in tf_clean:
        try:
            tf_minutes = int(tf_clean.replace('min', ''))
        except:
            tf_minutes = 15
    elif 'hr' in tf_clean:
        try:
            tf_minutes = int(tf_clean.replace('hr', '')) * 60
        except:
            tf_minutes = 60
    elif 'day' in tf_clean:
        try:
            tf_minutes = int(tf_clean.replace(' day', '').replace('day', '')) * 1440
        except:
            tf_minutes = 1440
    elif 'week' in tf_clean:
        tf_minutes = 10080  # 7 days
    elif 'month' in tf_clean:
        tf_minutes = 43200  # 30 days
    else:
        tf_minutes = 15  # default to 15min

    # Adaptation sensitivity: Medium (1.0), High (1.4), Low (0.7)
    adapt_mult = 1.0  # Medium sensitivity

    # Auto-calculate adaptive lengths using logarithmic scaling
    # Formula calibrated for crypto scalping (matching TradingView script)
    auto_rsi_length = int(np.clip(
        np.round(5 + np.log10(tf_minutes + 1) * 6 * adapt_mult),
        5, 35
    ))

    auto_vwma_period = int(np.clip(
        np.round(10 + np.log10(tf_minutes + 1) * 8 * adapt_mult),
        10, 50
    ))

    auto_tema_length = int(np.clip(
        np.round(4 + np.log10(tf_minutes + 1) * 5 * adapt_mult),
        3, 100
    ))

    # =================================================================
    # RSI CALCULATION BASED ON MODE
    # =================================================================
    if rsi_mode == 'ALMA Fixed':
        # ALMA Fixed: Use ALMA smoothing with user-defined fixed lengths
        logging.info(f"  HILEGA ALMA Fixed | TF={tf_input} | RSI={fixed_rsi_length} | VWMA={fixed_vwma_length} | TEMA={fixed_tema_length}")
        true_rsi = calculate_true_rsi_alma(close, length=fixed_rsi_length)
        vwma_rsi = calculate_vwma(true_rsi, volume, length=fixed_vwma_length)
        tema_rsi = calculate_tema_of_series(true_rsi, length=fixed_tema_length)

    elif rsi_mode == 'ALMA':
        # ALMA (Adaptive): Use ALMA smoothing with timeframe-adaptive lengths
        logging.info(f"  HILEGA ALMA Adaptive | TF={tf_input} ({tf_minutes}min) | RSI={auto_rsi_length} | VWMA={auto_vwma_period} | TEMA={auto_tema_length}")
        rsi_lengths = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 24, 26, 28, 30, 35]
        rsis = {}
        for length in rsi_lengths:
            rsis[length] = calculate_true_rsi_alma(close, length=length)

        # SELECT RSI based on auto_rsi_length using np.select
        rsi_conditions = [auto_rsi_length <= length for length in rsi_lengths]
        rsi_values = [rsis[length] for length in rsi_lengths]
        true_rsi = np.select(rsi_conditions, rsi_values, default=rsis[35])
        true_rsi = pd.Series(true_rsi, index=close.index)

        vwma_rsi = calculate_vwma(true_rsi, volume, length=auto_vwma_period)
        tema_rsi = calculate_tema_of_series(true_rsi, length=auto_tema_length)

    elif rsi_mode == 'RMA':
        # RMA (Adaptive): Use RMA smoothing with timeframe-adaptive lengths
        logging.info(f"  HILEGA RMA Adaptive | TF={tf_input} ({tf_minutes}min) | RSI={auto_rsi_length} | VWMA={auto_vwma_period} | TEMA={auto_tema_length}")
        rsi_lengths = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 24, 26, 28, 30, 35]
        rsis = {}
        for length in rsi_lengths:
            rsis[length] = calculate_true_rsi(close, length=length)

        # SELECT RSI based on auto_rsi_length using np.select
        rsi_conditions = [auto_rsi_length <= length for length in rsi_lengths]
        rsi_values = [rsis[length] for length in rsi_lengths]
        true_rsi = np.select(rsi_conditions, rsi_values, default=rsis[35])
        true_rsi = pd.Series(true_rsi, index=close.index)

        vwma_rsi = calculate_vwma(true_rsi, volume, length=auto_vwma_period)
        tema_rsi = calculate_tema_of_series(true_rsi, length=auto_tema_length)

    else:
        # Default to ALMA Fixed if unknown mode
        logging.warning(f"Unknown RSI mode '{rsi_mode}', defaulting to ALMA Fixed")
        true_rsi = calculate_true_rsi_alma(close, length=fixed_rsi_length)
        vwma_rsi = calculate_vwma(true_rsi, volume, length=fixed_vwma_length)
        tema_rsi = calculate_tema_of_series(true_rsi, length=fixed_tema_length)

    # Get the last value (latest candle - includes forming candle for real-time values)
    current_true_rsi = true_rsi.iloc[-1]
    current_tema = tema_rsi.iloc[-1]
    current_vwma = vwma_rsi.iloc[-1]

    # Calculate RSI-TEMA Gap
    rsi_tema_gap = current_true_rsi - current_tema

    # Calculate Angle (rate of change of the gap)
    if len(true_rsi) >= 2:
        prev_gap = true_rsi.iloc[-2] - tema_rsi.iloc[-2]
        angle = np.degrees(np.arctan(rsi_tema_gap - prev_gap))
    else:
        angle = 0.0

    # Signal detection logic
    signal = None

    if scanner_mode == 'buy':
        threshold = rsi_threshold if rsi_threshold is not None else 10
        if current_true_rsi <= threshold:
            signal = 'LONG'
    elif scanner_mode == 'sell':
        threshold = rsi_threshold if rsi_threshold is not None else 90
        if current_true_rsi >= threshold:
            signal = 'SHORT'

    return signal, angle, rsi_tema_gap, current_true_rsi, current_vwma

def apply_qwen_scanner(df, tf_input="1 day", use_current_candle=False, **kwargs):
    """
    Applies the MA Qwen indicator logic (matching QwenPre alert):
    1. Volatility & Regime detection (lowVol, highVolMomentum, panicSelling)
    2. Indicators: EMA(12), EMA(26), RSI(14), Volume Spike, Bollinger Bands
    3. Strategy modes: mean_reversion, trend, neutral
    4. longCondition / shortCondition computed for all bars
    5. buyToPlot / sellToPlot with 5-bar dedup (no repeated QL/QS within 5 bars)
    6. Signal = buyToPlot or sellToPlot on the latest CLOSED candle (= QwenPre)

    If use_current_candle=True, the forming candle is kept (for "Now" mode).

    Returns: (signal, None, None) — angle/tema_gap not applicable for Qwen
    """
    if df is None or len(df) < 100:
        return None, None, None

    if not use_current_candle:
        # Drop the last row (current forming/incomplete candle)
        df = df.iloc[:-1].copy()

    if len(df) < 100:
        return None, None, None

    try:
        # === INPUTS ===
        i_volLookbackHours = 24

        # === Timeframe Handling ===
        tf_clean = tf_input.lower().strip()
        if 'min' in tf_clean:
            try:
                timeframe_in_minutes = int(tf_clean.replace('min', ''))
            except:
                timeframe_in_minutes = 15
        elif 'hr' in tf_clean:
            try:
                timeframe_in_minutes = int(tf_clean.replace('hr', '')) * 60
            except:
                timeframe_in_minutes = 60
        elif 'day' in tf_clean:
            timeframe_in_minutes = 1440
        elif 'week' in tf_clean:
            timeframe_in_minutes = 10080
        else:
            timeframe_in_minutes = 15

        bars_per_hour = 60 / max(1, timeframe_in_minutes)
        vol_lookback_bars = max(20, round(i_volLookbackHours * bars_per_hour))

        # === Volatility & Regime ===
        df['pctReturn'] = (df['close'] - df['close'].shift(1)) / df['close'].shift(1)
        df['volatility_q'] = df['pctReturn'].rolling(window=vol_lookback_bars, min_periods=1).std()

        # priceChange24h = close / close[vol_lookback_bars] - 1
        shift_bars = min(vol_lookback_bars, len(df) - 1)
        df['priceChange24h'] = df['close'] / df['close'].shift(shift_bars) - 1
        df['priceChange24h'] = df['priceChange24h'].fillna(0)

        df['lowVol'] = (df['volatility_q'] < 0.012) & (df['priceChange24h'].abs() < 0.008)
        df['highVolMomentum'] = (df['volatility_q'] > 0.035) & (df['priceChange24h'] > 0.025)
        df['panicSelling'] = df['priceChange24h'] < -0.03

        # === Indicators ===
        df['emaFast12'] = calculate_ema(df['close'], 12)
        df['emaSlow26'] = calculate_ema(df['close'], 26)
        df['rsi'] = calculate_rsi(df['close'], 14)
        df['volumeSMA30'] = df['volume'].rolling(window=30, min_periods=1).mean()
        df['volumeSpike'] = df['volume'] > df['volumeSMA30'] * 1.3

        # Bollinger Bands (adaptive)
        n = len(df)
        bb_upper = pd.Series(np.nan, index=df.index)
        bb_lower = pd.Series(np.nan, index=df.index)

        for i in range(max(24, 0), n):
            vol_val = df['volatility_q'].iloc[i] if not pd.isna(df['volatility_q'].iloc[i]) else 0
            bb_length = 14 if vol_val > 0.03 else 24
            start = max(0, i - bb_length + 1)
            window = df['close'].iloc[start:i + 1]
            basis = window.mean()
            dev = window.std()
            if not pd.isna(dev):
                bb_upper.iloc[i] = basis + 2.1 * dev
                bb_lower.iloc[i] = basis - 2.1 * dev

        df['bbUpper'] = bb_upper
        df['bbLower'] = bb_lower

        # VWAP (only for neutral mode)
        df['vwap'] = calculate_vwap(df)

        # === Strategy Logic ===
        # Determine mode for each bar
        modes = []
        for i in range(n):
            if df['lowVol'].iloc[i]:
                modes.append('mean_reversion')
            elif df['highVolMomentum'].iloc[i] or df['panicSelling'].iloc[i]:
                modes.append('trend')
            else:
                modes.append('neutral')
        df['mode'] = modes

        # =================================================================
        # COMPUTE longCondition / shortCondition FOR ALL BARS
        # =================================================================
        # We need all bars to apply the 5-bar deduplication that
        # determines buyToPlot / sellToPlot (matching Pine Script).
        long_cond = np.zeros(n, dtype=bool)
        short_cond = np.zeros(n, dtype=bool)

        close_vals = df['close'].values
        ema_fast_vals = df['emaFast12'].values
        ema_slow_vals = df['emaSlow26'].values
        rsi_vals = df['rsi'].values
        bb_up_vals = df['bbUpper'].values
        bb_lo_vals = df['bbLower'].values
        vwap_vals = df['vwap'].values
        high_vol_mom_vals = df['highVolMomentum'].values
        panic_vals = df['panicSelling'].values
        vol_spike_vals = df['volumeSpike'].values

        for i in range(1, n):
            m = modes[i]
            if m == 'mean_reversion':
                if not np.isnan(bb_lo_vals[i]) and not np.isnan(rsi_vals[i]):
                    long_cond[i] = (close_vals[i] <= bb_lo_vals[i]) and (rsi_vals[i] < 28) and (close_vals[i] < ema_slow_vals[i])
                    short_cond[i] = (close_vals[i] >= bb_up_vals[i]) and (rsi_vals[i] > 72) and (close_vals[i] > ema_slow_vals[i])
            elif m == 'trend':
                if high_vol_mom_vals[i] or (panic_vals[i] and rsi_vals[i] < 25 and vol_spike_vals[i]):
                    long_cond[i] = (close_vals[i] > ema_fast_vals[i]) and (ema_fast_vals[i] > ema_slow_vals[i])
                short_cond[i] = False  # Conservative: no shorts in panic
            else:  # neutral
                if not np.isnan(vwap_vals[i]):
                    long_cond[i] = (close_vals[i] > ema_fast_vals[i]) and (ema_fast_vals[i] > ema_slow_vals[i]) and (close_vals[i] > vwap_vals[i])
                    short_cond[i] = (close_vals[i] < ema_fast_vals[i]) and (ema_fast_vals[i] < ema_slow_vals[i]) and (close_vals[i] < vwap_vals[i])

        # =================================================================
        # 5-BAR DEDUPLICATION — matches Pine Script buyToPlot / sellToPlot
        # =================================================================
        # buyToPlot = longCondition AND no longCondition in prior 5 bars
        # This IS part of the indicator logic (not just visual).
        lookback_bars = 5
        last_idx = n - 1

        # Check buyToPlot on the last closed candle
        buy_to_plot = False
        if long_cond[last_idx]:
            had_recent_buy = False
            for j in range(1, min(lookback_bars + 1, last_idx + 1)):
                if long_cond[last_idx - j]:
                    had_recent_buy = True
                    break
            buy_to_plot = not had_recent_buy

        # Check sellToPlot on the last closed candle
        sell_to_plot = False
        if short_cond[last_idx]:
            had_recent_sell = False
            for j in range(1, min(lookback_bars + 1, last_idx + 1)):
                if short_cond[last_idx - j]:
                    had_recent_sell = True
                    break
            sell_to_plot = not had_recent_sell

        # =================================================================
        # SIGNAL — matches QwenPre alert (buyToPlot[1] / sellToPlot[1])
        # =================================================================
        # We dropped the forming candle already, so df.iloc[-1] IS the
        # "previous closed candle" = [1] from the current forming bar.
        signal = None
        if buy_to_plot:
            signal = "LONG"
        elif sell_to_plot:
            signal = "SHORT"

        if signal:
            last_ts = df.index[-1]
            logging.info(f"  >>> Qwen {signal} signal on latest closed candle {last_ts}")

        # Debug logging for the last candle
        logging.info(
            f"  Qwen debug | mode={modes[last_idx]} | "
            f"close={close_vals[last_idx]:.4f} | "
            f"emaFast={ema_fast_vals[last_idx]:.4f} emaSlow={ema_slow_vals[last_idx]:.4f} | "
            f"rsi={rsi_vals[last_idx]:.2f} | "
            f"longCond={long_cond[last_idx]} shortCond={short_cond[last_idx]} | "
            f"buyToPlot={buy_to_plot} sellToPlot={sell_to_plot}"
        )

        # Capture RSI value at signal time
        rsi_value = round(float(rsi_vals[last_idx]), 2) if signal and not np.isnan(rsi_vals[last_idx]) else None

        # Capture Open and Close values at signal time
        open_value = round(float(df['open'].iloc[last_idx]), 8) if signal and 'open' in df.columns and not pd.isna(df['open'].iloc[last_idx]) else None
        close_value = round(float(close_vals[last_idx]), 8) if signal and not np.isnan(close_vals[last_idx]) else None

        return signal, None, None, rsi_value, open_value, close_value

    except Exception as e:
        logging.error(f"Error in Qwen calculation: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return None, None, None, None, None, None

# =============================================================================
# MAIN SCAN ENTRY POINT
# =============================================================================

async def scan_single_symbol(symbol, timeframes, kwargs, results_list, semaphore, daily_change):
    """
    Scans a single symbol across all requested timeframes.
    Uses a semaphore to limit concurrent requests.
    Supports scanner_type: 'ama_pro', 'qwen', 'both', 'ama_pro_now', 'qwen_now', 'both_now', 'all'
    Or a list of scanner types: ['ama_pro', 'ama_pro_now']
    """
    adaptation_speed = kwargs.get('adaptation_speed', 'Medium')
    min_bars_between = kwargs.get('min_bars_between', 3)
    scanner_type = kwargs.get('scanner_type', 'ama_pro')
    hilega_buy_rsi = kwargs.get('hilega_buy_rsi', 10)
    hilega_sell_rsi = kwargs.get('hilega_sell_rsi', 90)
    hilega_rsi_mode = kwargs.get('hilega_rsi_mode', 'ALMA Fixed')
    alma_fixed_rsi_length = kwargs.get('alma_fixed_rsi_length', 11)
    alma_fixed_vwma_length = kwargs.get('alma_fixed_vwma_length', 21)
    alma_fixed_tema_length = kwargs.get('alma_fixed_tema_length', 10)

    # Support for multiple scanner types (list) or single scanner type (string)
    if isinstance(scanner_type, list):
        # List of specific scanners requested
        run_ama = 'ama_pro' in scanner_type or 'both' in scanner_type or 'all' in scanner_type
        run_qwen = 'qwen' in scanner_type or 'both' in scanner_type or 'all' in scanner_type
        run_ama_now = 'ama_pro_now' in scanner_type or 'both_now' in scanner_type or 'all' in scanner_type
        run_qwen_now = 'qwen_now' in scanner_type or 'both_now' in scanner_type or 'all' in scanner_type
        run_hilega_buy = 'hilega_buy' in scanner_type
        run_hilega_sell = 'hilega_sell' in scanner_type
        run_cross_up = 'rsi_cross_up_vwma' in scanner_type
        run_cross_down = 'rsi_cross_dn_vwma' in scanner_type
    else:
        # Single scanner type (original logic)
        run_ama = scanner_type in ('ama_pro', 'both', 'all')
        run_qwen = scanner_type in ('qwen', 'both', 'all')
        run_ama_now = scanner_type in ('ama_pro_now', 'both_now', 'all')
        run_qwen_now = scanner_type in ('qwen_now', 'both_now', 'all')
        run_hilega_buy = scanner_type == 'hilega_buy'
        run_hilega_sell = scanner_type == 'hilega_sell'
        run_cross_up = scanner_type == 'rsi_cross_up_vwma'
        run_cross_down = scanner_type == 'rsi_cross_dn_vwma'

    async with semaphore:
        for tf in timeframes:
            try:
                df = await fetch_binance_data(symbol, tf)
                if df is None:
                    continue

                loop = asyncio.get_event_loop()
                ama_signal = None
                qwen_signal = None

                # Run AMA Pro scanner
                if run_ama and len(df) >= 200:
                    signal, angle, tema_gap, rsi, open_val, close_val, sig_type = await loop.run_in_executor(
                        executor,
                        lambda tf=tf: apply_ama_pro_tema(
                            df.copy(),
                            tf_input=tf,
                            adaptation_speed=adaptation_speed,
                            min_bars_between=min_bars_between
                        )
                    )
                    if signal:
                        ama_signal = (signal, angle, tema_gap, rsi, open_val, close_val, sig_type)

                # Run Qwen scanner
                if run_qwen and len(df) >= 100:
                    signal_q, _, _, rsi_q, open_val_q, close_val_q = await loop.run_in_executor(
                        executor,
                        lambda tf=tf: apply_qwen_scanner(
                            df.copy(),
                            tf_input=tf
                        )
                    )
                    if signal_q:
                        qwen_signal = (signal_q, rsi_q, open_val_q, close_val_q)

                # Run AMA Pro Now scanner (current/forming candle)
                ama_now_signal = None
                if run_ama_now and len(df) >= 200:
                    signal, angle, tema_gap, rsi, open_val, close_val, sig_type = await loop.run_in_executor(
                        executor,
                        lambda tf=tf: apply_ama_pro_tema(
                            df.copy(),
                            tf_input=tf,
                            use_current_candle=True,
                            adaptation_speed=adaptation_speed,
                            min_bars_between=min_bars_between
                        )
                    )
                    if signal:
                        ama_now_signal = (signal, angle, tema_gap, rsi, open_val, close_val, sig_type)

                # Run Qwen Now scanner (current/forming candle)
                qwen_now_signal = None
                if run_qwen_now and len(df) >= 100:
                    signal_q, _, _, rsi_q, open_val_q, close_val_q = await loop.run_in_executor(
                        executor,
                        lambda tf=tf: apply_qwen_scanner(
                            df.copy(),
                            tf_input=tf,
                            use_current_candle=True
                        )
                    )
                    if signal_q:
                        qwen_now_signal = (signal_q, rsi_q, open_val_q, close_val_q)

                # ── Helper to append a result row ──
                def add_result(sig, angle_val, tg_val, scanner_label, rsi_val=None, open_val=None, close_val=None, sig_type=None):
                    # Determine color based on Open vs Close
                    color = "N/A"
                    if open_val is not None and close_val is not None:
                        if open_val < close_val:
                            color = "GREEN"
                        elif open_val > close_val:
                            color = "RED"
                        else:
                            color = "NEUTRAL"

                    # Append signal type to scanner label if it's an ENTRY signal
                    if sig_type == "ENTRY":
                        # Make it clear this is from a previous candle confirmation
                        if "Now" in scanner_label:
                            scanner_label = f"{scanner_label} (Entry)"
                        else:
                            scanner_label = f"{scanner_label} Previous (Entry)"

                    results_list.append({
                        'Crypto Name': symbol,
                        'Timeperiod': tf,
                        'Signal': sig,
                        'Angle': f"{angle_val:.2f}°" if angle_val is not None else "N/A",
                        'TEMA Gap': f"{tg_val:+.3f}%" if tg_val is not None else "N/A",
                        'RSI': f"{rsi_val:.2f}" if rsi_val is not None else "N/A",
                        'Daily Change': daily_change,
                        'Scanner': scanner_label,
                        'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'Color': color,
                        'Signal Type': sig_type or 'CROSSOVER'
                    })

                # ── Build results for closed-candle scanners (AMA Pro / Qwen) ──
                if run_ama and run_qwen:
                    # "Both" or "All" mode for closed-candle pair
                    if ama_signal and qwen_signal:
                        if ama_signal[0] == qwen_signal[0]:
                            add_result(ama_signal[0], ama_signal[1], ama_signal[2], 'Both', ama_signal[3], ama_signal[4], ama_signal[5], ama_signal[6])
                        else:
                            add_result(ama_signal[0], ama_signal[1], ama_signal[2], 'AMA Pro', ama_signal[3], ama_signal[4], ama_signal[5], ama_signal[6])
                            add_result(qwen_signal[0], None, None, 'Qwen', qwen_signal[1], qwen_signal[2], qwen_signal[3], None)
                    elif ama_signal:
                        add_result(ama_signal[0], ama_signal[1], ama_signal[2], 'AMA Pro', ama_signal[3], ama_signal[4], ama_signal[5], ama_signal[6])
                    elif qwen_signal:
                        add_result(qwen_signal[0], None, None, 'Qwen', qwen_signal[1], qwen_signal[2], qwen_signal[3], None)
                elif run_ama and ama_signal:
                    add_result(ama_signal[0], ama_signal[1], ama_signal[2], 'AMA Pro', ama_signal[3], ama_signal[4], ama_signal[5], ama_signal[6])
                elif run_qwen and qwen_signal:
                    add_result(qwen_signal[0], None, None, 'Qwen', qwen_signal[1], qwen_signal[2], qwen_signal[3], None)

                # ── Build results for current-candle scanners (AMA Pro Now / Qwen Now) ──
                if run_ama_now and run_qwen_now:
                    # "Both Now" or "All" mode for current-candle pair
                    if ama_now_signal and qwen_now_signal:
                        if ama_now_signal[0] == qwen_now_signal[0]:
                            add_result(ama_now_signal[0], ama_now_signal[1], ama_now_signal[2], 'Both Now', ama_now_signal[3], ama_now_signal[4], ama_now_signal[5], ama_now_signal[6])
                        else:
                            add_result(ama_now_signal[0], ama_now_signal[1], ama_now_signal[2], 'AMA Pro Now', ama_now_signal[3], ama_now_signal[4], ama_now_signal[5], ama_now_signal[6])
                            add_result(qwen_now_signal[0], None, None, 'Qwen Now', qwen_now_signal[1], qwen_now_signal[2], qwen_now_signal[3], None)
                    elif ama_now_signal:
                        add_result(ama_now_signal[0], ama_now_signal[1], ama_now_signal[2], 'AMA Pro Now', ama_now_signal[3], ama_now_signal[4], ama_now_signal[5], ama_now_signal[6])
                    elif qwen_now_signal:
                        add_result(qwen_now_signal[0], None, None, 'Qwen Now', qwen_now_signal[1], qwen_now_signal[2], qwen_now_signal[3], None)
                elif run_ama_now and ama_now_signal:
                    add_result(ama_now_signal[0], ama_now_signal[1], ama_now_signal[2], 'AMA Pro Now', ama_now_signal[3], ama_now_signal[4], ama_now_signal[5], ama_now_signal[6])
                elif run_qwen_now and qwen_now_signal:
                    add_result(qwen_now_signal[0], None, None, 'Qwen Now', qwen_now_signal[1], qwen_now_signal[2], qwen_now_signal[3], None)

                # ── HILEGA SCANNER LOGIC ──
                # HILEGA uses a different result structure and is mutually exclusive with AMA/Qwen
                if run_hilega_buy or run_hilega_sell:
                    # HILEGA BUY scanner
                    if run_hilega_buy and len(df) >= 100:
                        signal, angle, rsi_tema_gap, true_rsi, vwma_rsx = await loop.run_in_executor(
                            executor,
                            lambda tf=tf: apply_hilega_scanner(
                                df.copy(),
                                scanner_mode='buy',
                                rsi_threshold=hilega_buy_rsi,
                                tf_input=tf,
                                rsi_mode=hilega_rsi_mode,
                                fixed_rsi_length=alma_fixed_rsi_length,
                                fixed_vwma_length=alma_fixed_vwma_length,
                                fixed_tema_length=alma_fixed_tema_length
                            )
                        )
                        if signal:
                            results_list.append({
                                'Crypto Name': symbol,
                                'Timeperiod': tf,
                                'Signal': signal,
                                'Angle': f"{angle:.2f}°" if angle is not None else "N/A",
                                'RSI-TEMA': f"{rsi_tema_gap:+.2f}" if rsi_tema_gap is not None else "N/A",
                                'RSI': f"{true_rsi:.2f}" if true_rsi is not None else "N/A",
                                'VWMA': f"{vwma_rsx:.2f}" if vwma_rsx is not None else "N/A",
                                'Daily Change': daily_change,
                                'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                'Scanner': 'HILEGA BUY'
                            })

                    # HILEGA SELL scanner
                    if run_hilega_sell and len(df) >= 100:
                        signal, angle, rsi_tema_gap, true_rsi, vwma_rsx = await loop.run_in_executor(
                            executor,
                            lambda tf=tf: apply_hilega_scanner(
                                df.copy(),
                                scanner_mode='sell',
                                rsi_threshold=hilega_sell_rsi,
                                tf_input=tf,
                                rsi_mode=hilega_rsi_mode,
                                fixed_rsi_length=alma_fixed_rsi_length,
                                fixed_vwma_length=alma_fixed_vwma_length,
                                fixed_tema_length=alma_fixed_tema_length
                            )
                        )
                        if signal:
                            results_list.append({
                                'Crypto Name': symbol,
                                'Timeperiod': tf,
                                'Signal': signal,
                                'Angle': f"{angle:.2f}°" if angle is not None else "N/A",
                                'RSI-TEMA': f"{rsi_tema_gap:+.2f}" if rsi_tema_gap is not None else "N/A",
                                'RSI': f"{true_rsi:.2f}" if true_rsi is not None else "N/A",
                                'VWMA': f"{vwma_rsx:.2f}" if vwma_rsx is not None else "N/A",
                                'Daily Change': daily_change,
                                'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                'Scanner': 'HILEGA SELL'
                            })

                # ── ADAPTIVE HTF CROSS SCANNER LOGIC ──
                # Cross scanner uses a different result structure and is mutually exclusive with AMA/HILEGA
                if run_cross_up or run_cross_down:
                    # RSI Cross UP VWMA scanner
                    if run_cross_up and len(df) >= 100:
                        signal, angle, rsi_vwma_diff, rsi_val, vwma_val, alma_val, candle_status = await loop.run_in_executor(
                            executor,
                            lambda tf=tf: apply_adaptive_htf_cross_scanner(
                                df.copy(),
                                scanner_mode='cross_up',
                                tf_input=tf
                            )
                        )
                        if signal:
                            signal_type = "Cross UP"
                            results_list.append({
                                'Crypto Name': symbol,
                                'Timeperiod': tf,
                                'Signal Type': signal_type,
                                'Candle Status': candle_status or 'N/A',
                                'Angle': f"{angle:.2f}%" if angle is not None else "N/A",
                                'RSI-VWMA': f"{rsi_vwma_diff:+.2f}" if rsi_vwma_diff is not None else "N/A",
                                'RSI': f"{rsi_val:.2f}" if rsi_val is not None else "N/A",
                                'VWMA': f"{vwma_val:.2f}" if vwma_val is not None else "N/A",
                                'ALMA': f"{alma_val:.2f}" if alma_val is not None else "N/A",
                                'Daily Change': daily_change,
                                'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                'Scanner': 'RSI CROSS UP VWMA'
                            })

                    # RSI Cross DN VWMA scanner
                    if run_cross_down and len(df) >= 100:
                        signal, angle, rsi_vwma_diff, rsi_val, vwma_val, alma_val, candle_status = await loop.run_in_executor(
                            executor,
                            lambda tf=tf: apply_adaptive_htf_cross_scanner(
                                df.copy(),
                                scanner_mode='cross_down',
                                tf_input=tf
                            )
                        )
                        if signal:
                            signal_type = "Cross DN"
                            results_list.append({
                                'Crypto Name': symbol,
                                'Timeperiod': tf,
                                'Signal Type': signal_type,
                                'Candle Status': candle_status or 'N/A',
                                'Angle': f"{angle:.2f}%" if angle is not None else "N/A",
                                'RSI-VWMA': f"{rsi_vwma_diff:+.2f}" if rsi_vwma_diff is not None else "N/A",
                                'RSI': f"{rsi_val:.2f}" if rsi_val is not None else "N/A",
                                'VWMA': f"{vwma_val:.2f}" if vwma_val is not None else "N/A",
                                'ALMA': f"{alma_val:.2f}" if alma_val is not None else "N/A",
                                'Daily Change': daily_change,
                                'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                'Scanner': 'RSI CROSS DN VWMA'
                            })

            except Exception as e:
                logging.error(f"Error scanning {symbol} on {tf}: {str(e)}")

async def run_scan(indices, timeframes, log_file, **kwargs):
    """
    Main entrypoint called by the API for Gemini_Crypto (Async).
    Scans top crypto symbols from Binance in parallel.
    Uses batching to prevent hanging and allow UI responsiveness.
    """
    results = []
    crypto_count = kwargs.get('crypto_count', 20)
    
    # Use max 15 concurrent requests to Binance to stay safe with rate limits
    semaphore = asyncio.Semaphore(15)

    # Fetch top coins (uses cache if available)
    top_coins = await get_top_binance_symbols(limit=crypto_count)
    if not top_coins:
        logging.error("No symbols to scan.")
        return []
    
    # Batch the processing of symbols to prevent overwhelming the connection pool
    batch_size = 20
    for i in range(0, len(top_coins), batch_size):
        batch = top_coins[i:i + batch_size]
        tasks = []
        for coin in batch:
            change_val = coin.get('change', 0)
            if change_val is None:
                change_val = 0
            change_str = f"{float(change_val):+.2f}%"
            tasks.append(scan_single_symbol(coin['symbol'], timeframes, kwargs, results, semaphore, change_str))
        
        if tasks:
            logging.info(f"==> Scanning batch {i//batch_size + 1} ({len(batch)} symbols)...")
            await asyncio.gather(*tasks)
        
        # Yield control back to event loop to allow other requests (like /api/logs)
        await asyncio.sleep(0.1)
    
    logging.info(f"Scan complete. Total signals found: {len(results)}")
    return results
