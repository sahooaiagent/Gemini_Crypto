"""
OB/OS Scanner
=============
Overbought / Oversold scanner using HILEGA True RSI crossover / crossunder its ALMA.

True RSI formula (exact Pine Script match):
    delta = src - src[1]
    up    = delta > 0 ? delta : 0
    down  = delta < 0 ? -delta : 0
    maUp   = ta.alma(up,   length, 0.85, 5)   ← sigma=5 for internal True RSI ALMA
    maDown = ta.alma(down, length, 0.85, 5)
    rs = maUp / maDown
    TrueRSI = 100 - (100 / (1 + rs))

ALMA of RSI (signal line):
    ta.alma(rsx, alma_len_final, 0.85, 6.0)   ← sigma=6 for the MA plotted on RSI

Auto-Adaptive lengths (matches Pine Script getHigherTF / adaptMult logic):
    higherTFMinutes is derived from the bar's timeframe.
    rsi_len  = max(7,  min(35,  round(9  + log10(higherTFMinutes+1) * 7  * adaptMult)))
    alma_len = max(6,  min(100, round(8  + log10(higherTFMinutes+1) * 6  * adaptMult)))
"""

import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import logging
import math
from typing import List, Optional

# ── Reuse the exact HILEGA indicator functions from scanner.py ──
from scanner import (
    calculate_true_rsi_alma,    # True RSI: ALMA(up/down, length, offset=0.85, sigma=5)
    calculate_alma,             # ALMA MA:  ALMA(rsi,     length, offset=0.85, sigma=6)
    calculate_tema_of_series,   # TEMA of a series (alternative MA)
)

# ── Shared exchange instance ──
_exchange = None

def _get_exchange():
    global _exchange
    if _exchange is None:
        _exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'},
        })
    return _exchange

async def close_exchange():
    global _exchange
    if _exchange is not None:
        await _exchange.close()
        _exchange = None

# ── Timeframe mapping: UI label → ccxt string + minutes ──
TF_MAP = {
    '1min':   ('1m',   1),
    '3min':   ('3m',   3),
    '5min':   ('5m',   5),
    '10min':  ('15m',  10),   # ccxt uses 15m as closest; minutes used for adaptation
    '15min':  ('15m',  15),
    '30min':  ('30m',  30),
    '1hr':    ('1h',   60),
    '2hr':    ('2h',   120),
    '4hr':    ('4h',   240),
    '6hr':    ('6h',   360),
    '12hr':   ('12h',  720),
    '1 day':  ('1d',   1440),
    '1 week': ('1w',   10080),
}

# =============================================================================
# STANDARD WILDER RSI (fallback when rsi_type='Standard')
# =============================================================================

def _rsi_standard(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's RSI (RMA smoothing) — used when user selects Standard mode."""
    delta = close.diff()
    gain = pd.Series(np.where(delta > 0, delta, 0), index=close.index)
    loss = pd.Series(np.where(delta < 0, -delta, 0), index=close.index)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


# =============================================================================
# AUTO-ADAPTIVE LENGTH CALCULATION  (matches Pine Script exactly)
# =============================================================================

def _get_higher_tf_minutes(tf_minutes: int) -> int:
    """
    Pine Script getHigherTF() — maps current TF to a higher reference TF.
    Used to derive adaptive RSI / ALMA lengths.
    """
    if   tf_minutes <= 5:    return 60
    elif tf_minutes <= 15:   return 240
    elif tf_minutes <= 30:   return 1440
    elif tf_minutes <= 60:   return 10080
    elif tf_minutes <= 240:  return 10080
    elif tf_minutes <= 2880: return 43200
    elif tf_minutes <= 10080:return 525600
    else:                    return 525600


def _adaptive_lengths(tf_label: str, sensitivity: str = 'Medium') -> dict:
    """
    Compute adaptive RSI length and ALMA length for a given timeframe,
    matching the Pine Script formula exactly.

    Returns dict with keys: rsi_len, alma_len, higher_tf_min
    """
    adapt_mult = {'High': 1.2, 'Medium': 1.0, 'Low': 0.8}.get(sensitivity, 1.0)

    _, tf_min = TF_MAP.get(tf_label, ('1h', 60))
    higher_tf = _get_higher_tf_minutes(tf_min)
    log_val   = math.log10(higher_tf + 1)

    rsi_len  = max(7,  min(35,  round(9  + log_val * 7  * adapt_mult)))
    alma_len = max(6,  min(100, round(8  + log_val * 6  * adapt_mult)))

    return {'rsi_len': rsi_len, 'alma_len': alma_len, 'higher_tf_min': higher_tf}


# =============================================================================
# DATA FETCH
# =============================================================================

async def _fetch_ohlcv(symbol: str, tf_label: str, limit: int = 400) -> Optional[pd.DataFrame]:
    entry = TF_MAP.get(tf_label)
    if entry is None:
        return None
    ccxt_tf, _ = entry
    exchange = _get_exchange()
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, ccxt_tf, limit=limit)
        if not ohlcv or len(ohlcv) < 50:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        logging.debug(f"OB/OS fetch error {symbol} {tf_label}: {e}")
        return None


async def _get_top_symbols(limit: int = 50) -> List[dict]:
    """Return top Binance USDT spot symbols by 24 h quote volume."""
    exchange = _get_exchange()
    try:
        tickers = await exchange.fetch_tickers()
        usdt = [
            {'symbol': s, 'volume': t.get('quoteVolume') or 0,
             'price': t.get('last'), 'change': t.get('percentage')}
            for s, t in tickers.items()
            if s.endswith('/USDT') and ':' not in s
        ]
        usdt.sort(key=lambda x: x['volume'], reverse=True)
        return usdt[:limit]
    except Exception as e:
        logging.error(f"OB/OS get_top_symbols error: {e}")
        return []


# =============================================================================
# CORE SCAN LOGIC
# =============================================================================

async def _scan_symbol(
    symbol: str,
    timeframes: List[str],
    rsi_type: str,
    rsi_length: int,          # ignored when auto_adapt=True
    ma_type: str,
    ma_length: int,           # ignored when auto_adapt=True
    auto_adapt: bool,
    sensitivity: str,
    price: Optional[float],
    change: Optional[float],
    semaphore: asyncio.Semaphore,
) -> List[dict]:
    """
    Per-symbol scan across all timeframes.

    Signal logic (matches Pine Script):
      OS (Oversold)   : True RSI crossover  ALMA  — RSI rose from below to above the MA
      OB (Overbought) : True RSI crossunder ALMA  — RSI dropped from above to below the MA
    Detection uses the last 2 fully CLOSED candles (forming candle dropped).
    """
    results = []
    async with semaphore:
        for tf in timeframes:
            try:
                # ── Resolve lengths ──
                if auto_adapt:
                    lengths  = _adaptive_lengths(tf, sensitivity)
                    act_rsi  = lengths['rsi_len']
                    act_alma = lengths['alma_len']
                else:
                    act_rsi  = rsi_length
                    act_alma = ma_length

                df = await _fetch_ohlcv(symbol, tf)
                min_bars = max(act_rsi, act_alma) * 3 + 10
                if df is None or len(df) < min_bars:
                    continue

                # Drop forming (incomplete) candle — closed candles only
                closed = df.iloc[:-1]

                # ── True RSI (sigma=5, offset=0.85 inside gains/losses ALMA) ──
                if rsi_type == 'ALMA':
                    rsi_series = calculate_true_rsi_alma(closed['close'], length=act_rsi)
                else:
                    rsi_series = _rsi_standard(closed['close'], length=act_rsi)

                # ── MA of True RSI (ALMA sigma=6, offset=0.85 — or TEMA) ──
                if ma_type == 'TEMA':
                    ma_series = calculate_tema_of_series(rsi_series, length=act_alma)
                else:
                    # ALMA of RSI: sigma=6.0, offset=0.85 — matches Pine Script exactly
                    ma_series = calculate_alma(rsi_series, length=act_alma,
                                               offset=0.85, sigma=6.0)

                if len(rsi_series) < 2 or len(ma_series) < 2:
                    continue

                curr_rsi = float(rsi_series.iloc[-1])
                prev_rsi = float(rsi_series.iloc[-2])
                curr_ma  = float(ma_series.iloc[-1])
                prev_ma  = float(ma_series.iloc[-2])

                if any(np.isnan(v) for v in [curr_rsi, prev_rsi, curr_ma, prev_ma]):
                    continue

                # Crossover : RSI was below MA, now ≥ MA  → OS (Oversold / buy signal)
                # Crossunder: RSI was above MA, now ≤ MA  → OB (Overbought / sell signal)
                crossover  = (prev_rsi < prev_ma) and (curr_rsi >= curr_ma)
                crossunder = (prev_rsi > prev_ma) and (curr_rsi <= curr_ma)

                if not (crossover or crossunder):
                    continue

                signal    = 'OS' if crossover else 'OB'
                gap       = round(curr_rsi - curr_ma, 2)
                name      = symbol.replace('/USDT', '').replace(':USDT', '')
                price_str = f"{price:,.4f}" if price is not None else 'N/A'

                results.append({
                    'Name':       name,
                    'Symbol':     symbol,
                    'Timeframe':  tf,
                    'Signal':     signal,
                    'RSI':        round(curr_rsi, 2),
                    'MA':         round(curr_ma, 2),
                    'Gap':        gap,
                    'Prev_RSI':   round(prev_rsi, 2),
                    'Prev_MA':    round(prev_ma, 2),
                    'Price':      price_str,
                    'Change':     round(change if change is not None else 0.0, 2),
                    'RSI_Type':   rsi_type,
                    'RSI_Length': act_rsi,
                    'MA_Type':    ma_type,
                    'MA_Length':  act_alma,
                    'Auto_Adapt': auto_adapt,
                    'Sensitivity':sensitivity if auto_adapt else 'Manual',
                })
                logging.info(
                    f"  OB/OS | {name} {tf} → {signal} | "
                    f"RSI({act_rsi}) {prev_rsi:.2f}→{curr_rsi:.2f}  "
                    f"ALMA({act_alma}) {prev_ma:.2f}→{curr_ma:.2f}"
                )

            except Exception as e:
                logging.debug(f"OB/OS calc error {symbol} {tf}: {e}")
    return results


# =============================================================================
# ENTRY POINT
# =============================================================================

async def run_ob_os_scan(
    timeframes: List[str],
    crypto_count: int  = 50,
    rsi_type: str      = 'ALMA',
    rsi_length: int    = 11,      # used only when auto_adapt=False
    ma_type: str       = 'ALMA',
    ma_length: int     = 9,       # used only when auto_adapt=False
    auto_adapt: bool   = True,
    sensitivity: str   = 'Medium',
) -> List[dict]:
    """
    Main entry point.

    When auto_adapt=True (default):
        RSI length and ALMA length are computed per-timeframe using the
        Pine Script adaptive formula (same as HILEGA HTF indicator).
        Manual rsi_length / ma_length inputs are ignored.

    When auto_adapt=False:
        Uses the user-supplied rsi_length / ma_length for all timeframes.

    Signal logic
    ────────────
    OS = True RSI crossover  ALMA  (from below to above)  — Oversold / buy
    OB = True RSI crossunder ALMA  (from above to below)  — Overbought / sell
    """
    # Log adaptive lengths for each TF when auto_adapt is on
    if auto_adapt:
        for tf in timeframes:
            lns = _adaptive_lengths(tf, sensitivity)
            logging.info(
                f"  OB/OS adaptive | {tf} → higherTF={lns['higher_tf_min']}min "
                f"rsi_len={lns['rsi_len']}  alma_len={lns['alma_len']}"
            )

    logging.info(
        f"OB/OS Scan | TFs={timeframes} N={crypto_count} | "
        f"RSI={rsi_type} MA={ma_type} | "
        f"auto_adapt={auto_adapt} sensitivity={sensitivity}"
    )

    symbols_info = await _get_top_symbols(limit=crypto_count)
    if not symbols_info:
        logging.warning("OB/OS: no symbols fetched")
        return []

    semaphore = asyncio.Semaphore(8)
    tasks = [
        _scan_symbol(
            s['symbol'], timeframes,
            rsi_type, rsi_length,
            ma_type, ma_length,
            auto_adapt, sensitivity,
            s.get('price'), s.get('change'),
            semaphore,
        )
        for s in symbols_info
    ]

    nested = await asyncio.gather(*tasks, return_exceptions=True)
    results = []
    for r in nested:
        if isinstance(r, list):
            results.extend(r)

    os_results = [r for r in results if r['Signal'] == 'OS']
    ob_results = [r for r in results if r['Signal'] == 'OB']
    logging.info(f"OB/OS Scan done | OB={len(ob_results)} OS={len(os_results)}")
    return os_results + ob_results
