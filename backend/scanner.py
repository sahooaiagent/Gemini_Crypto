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
})

async def fetch_binance_data(symbol, timeframe, limit=500):
    """
    Fetches OHLCV data from Binance using CCXT (Async).
    """
    tf_map = {
        '15min': '15m',
        '30min': '30m',
        '45min': '15m',
        '1hr': '1h',
        '2hr': '2h',
        '4hr': '4h',
        '1 day': '1d',
        '1 week': '1w'
    }
    
    binance_tf = tf_map.get(timeframe, '15m')
    
    try:
        logging.info(f"Fetching {symbol} from Binance at {timeframe} interval...")
        # Use await for async fetch_ohlcv
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=binance_tf, limit=limit + 50)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        if timeframe == '45min':
            df = df.resample('45min').agg({
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
        
        # 4. Match top coins with Binance USDT pairs
        final_symbols = []
        for coin_sym in top_names:
            perp_symbol = f"{coin_sym}/USDT:USDT"
            spot_symbol = f"{coin_sym}/USDT"
            
            target = None
            if perp_symbol in markets:
                target = perp_symbol
            elif spot_symbol in markets:
                target = spot_symbol
            
            if target:
                ticker = tickers.get(target, {})
                final_symbols.append({
                    'symbol': target, 
                    'change': ticker.get('percentage', 0)
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

def apply_ama_pro_tema(df, tf_input="1 day", **kwargs):
    """
    Applies the full AMA PRO TEMA logic:
    1. Market regime detection (ADX, volatility ratio, EMA alignment)
    2. Adaptive TEMA period calculation (with tfMultiplier)
    3. TEMA crossover signals
    4. Signal filtering: longValid / shortValid (min bars between + regime conflict)
    5. Check the PREVIOUS closed candle (index -2) for a valid signal
    
    Returns: (signal, crossover_angle) or (None, None)
    """
    if df is None or len(df) < 200:
        return None, None

    # Drop the last row (current forming/incomplete candle) so all logic
    # runs exclusively on closed candles. After this, df.iloc[-1] is the
    # latest CLOSED candle.
    df = df.iloc[:-1].copy()

    if len(df) < 200:
        return None, None

    try:
        # === PINE SCRIPT PARAMETERS ===
        i_emaFastMin, i_emaFastMax = 8, 21
        i_emaSlowMin, i_emaSlowMax = 21, 55
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
        
        adaptive_fast = i_emaFastMin + fast_range * (1 - adjust_factor)
        adaptive_slow = i_emaSlowMin + slow_range * (1 - adjust_factor)
        
        # Ensure minimum separation of 6 (TEMA needs slightly larger)
        adaptive_slow = np.maximum(adaptive_slow, adaptive_fast + 6)
        
        # =================================================================
        # PRE-CALCULATE TEMA VALUES (matching Pine Script periods)
        # =================================================================
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
        
        # =================================================================
        # SECTION 5: STRATEGY LOGIC — TEMA crossovers
        # =================================================================
        df['longCondition'] = (df['temaFast'] > df['temaSlow']) & (df['temaFast'].shift(1) <= df['temaSlow'].shift(1))
        df['shortCondition'] = (df['temaFast'] < df['temaSlow']) & (df['temaFast'].shift(1) >= df['temaSlow'].shift(1))
        
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
        # SIGNAL CHECK — LATEST CLOSED CANDLE ONLY
        # =================================================================
        # The forming candle was already dropped before processing, so
        # df.iloc[-1] is the latest CLOSED candle.  Only report a signal
        # if longValid or shortValid fired on this candle — stale signals
        # from older candles are not actionable.

        signal = None
        crossover_angle = None

        last_row = df.iloc[-1]
        last_ts = df.index[-1]

        if last_row['longValid']:
            signal = "LONG"
        elif last_row['shortValid']:
            signal = "SHORT"

        if signal:
            logging.info(f"  >>> {signal} signal on latest closed candle {last_ts}")

            # Calculate crossover angle
            try:
                angle_lookback = 3
                if len(df) > angle_lookback + 1:
                    fast_now = df['temaFast'].iloc[-1]
                    fast_prev = df['temaFast'].iloc[-1 - angle_lookback]
                    slow_now = df['temaSlow'].iloc[-1]
                    slow_prev = df['temaSlow'].iloc[-1 - angle_lookback]
                    price = df['close'].iloc[-1]

                    fast_slope = (fast_now - fast_prev) / angle_lookback
                    slow_slope = (slow_now - slow_prev) / angle_lookback
                    slope_diff = (fast_slope - slow_slope) / price
                    crossover_angle = round(np.degrees(np.arctan(slope_diff * 100)), 2)
            except Exception:
                crossover_angle = 0.0
        else:
            logging.info(f"  No signal on latest closed candle {last_ts}.")
            
        return signal, crossover_angle
        
    except Exception as e:
        logging.error(f"Error in AMA PRO TEMA calculation: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return None, None

# =============================================================================
# MAIN SCAN ENTRY POINT
# =============================================================================

async def scan_single_symbol(symbol, timeframes, kwargs, results_list, semaphore, daily_change):
    """
    Scans a single symbol across all requested timeframes.
    Uses a semaphore to limit concurrent requests.
    """
    adaptation_speed = kwargs.get('adaptation_speed', 'Medium')
    min_bars_between = kwargs.get('min_bars_between', 3)
    
    async with semaphore:
        for tf in timeframes:
            try:
                df = await fetch_binance_data(symbol, tf)
                if df is not None and len(df) >= 200:
                    # Run CPU-intensive calculation in the thread pool to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    signal, angle = await loop.run_in_executor(
                        executor,
                        lambda: apply_ama_pro_tema(
                            df, 
                            tf_input=tf,
                            adaptation_speed=adaptation_speed, 
                            min_bars_between=min_bars_between
                        )
                    )
                    
                    if signal:
                        results_list.append({
                            'Crypto Name': symbol,
                            'Timeperiod': tf,
                            'Signal': signal,
                            'Angle': f"{angle:.2f}°" if angle is not None else "N/A",
                            'Daily Change': daily_change,
                            'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
