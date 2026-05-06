"""
OB/OS Scanner
=============
Dedicated Overbought / Oversold scanner using standard RSI or ALMA-based True RSI.
Scans top Binance crypto pairs across user-selected timeframes and returns
all assets currently in an OB or OS condition.
"""

import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import asyncio
import logging
from typing import List, Optional

# ── Reuse the exact HILEGA indicator functions from scanner.py ──
from scanner import (
    calculate_true_rsi_alma,   # True RSI with ALMA smoothing (sigma=5, offset=0.85)
    calculate_alma,            # ALMA MA (sigma=6, offset=0.85) — applied to the RSI series
    calculate_tema_of_series,  # TEMA of a series (used as MA of RSI)
)

# ── Shared exchange instance (reuse from scanner if already alive) ──
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

# ── Timeframe mapping: UI label → ccxt string ──
TF_MAP = {
    '1min':  '1m',
    '3min':  '3m',
    '5min':  '5m',
    '15min': '15m',
    '30min': '30m',
    '1hr':   '1h',
    '2hr':   '2h',
    '4hr':   '4h',
    '6hr':   '6h',
    '12hr':  '12h',
    '1 day': '1d',
    '1 week':'1w',
}

# =============================================================================
# INDICATOR FUNCTIONS
# =============================================================================
# All indicator functions are imported from scanner.py (the canonical HILEGA
# implementation) so there is a single source of truth.
#
#   calculate_true_rsi_alma(close, length)  — True RSI, ALMA sigma=5  (HILEGA ALMA)
#   calculate_alma(series, length)          — ALMA MA, sigma=6, offset=0.85
#   calculate_tema_of_series(series, length)— TEMA of a series
#
# Standard Wilder RSI (fallback when user selects "Standard"):

def _rsi_standard(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's RSI (RMA smoothing) — standard / non-True RSI."""
    delta = close.diff()
    gain = pd.Series(np.where(delta > 0, delta, 0), index=close.index)
    loss = pd.Series(np.where(delta < 0, -delta, 0), index=close.index)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


# =============================================================================
# DATA FETCH
# =============================================================================

async def _fetch_ohlcv(symbol: str, tf_label: str, limit: int = 300) -> Optional[pd.DataFrame]:
    ccxt_tf = TF_MAP.get(tf_label)
    if ccxt_tf is None:
        return None
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
    """Return top Binance USDT-margined spot symbols by 24 h volume."""
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

async def _scan_symbol(symbol: str, timeframes: List[str],
                       rsi_type: str, rsi_length: int,
                       ma_type: str, ma_length: int,
                       price: Optional[float], change: Optional[float],
                       semaphore: asyncio.Semaphore) -> List[dict]:
    """
    Signal detection:
      OS (Oversold)   : True RSI crossover  ALMA/TEMA  (RSI crosses from below to above)
      OB (Overbought) : True RSI crossunder ALMA/TEMA  (RSI crosses from above to below)
    Uses last 2 closed candles (drop forming candle).
    """
    results = []
    async with semaphore:
        for tf in timeframes:
            df = await _fetch_ohlcv(symbol, tf)
            min_bars = max(rsi_length, ma_length) + 20
            if df is None or len(df) < min_bars:
                continue
            try:
                # Drop forming (incomplete) candle — use only closed bars
                closed = df.iloc[:-1]

                # ── True RSI (exact HILEGA ALMA: sigma=5, offset=0.85) ──
                if rsi_type == 'ALMA':
                    rsi_series = calculate_true_rsi_alma(closed['close'], length=rsi_length)
                else:
                    rsi_series = _rsi_standard(closed['close'], length=rsi_length)

                # ── MA of the True RSI (ALMA sigma=6 or TEMA) ──
                if ma_type == 'TEMA':
                    ma_series = calculate_tema_of_series(rsi_series, length=ma_length)
                else:  # default ALMA
                    ma_series = calculate_alma(rsi_series, length=ma_length)

                # Need at least 2 valid values for crossover detection
                if len(rsi_series) < 2 or len(ma_series) < 2:
                    continue

                curr_rsi  = float(rsi_series.iloc[-1])
                prev_rsi  = float(rsi_series.iloc[-2])
                curr_ma   = float(ma_series.iloc[-1])
                prev_ma   = float(ma_series.iloc[-2])

                if any(np.isnan(v) for v in [curr_rsi, prev_rsi, curr_ma, prev_ma]):
                    continue

                # Crossover: RSI was below MA, now at or above → OS
                crossover  = (prev_rsi < prev_ma) and (curr_rsi >= curr_ma)
                # Crossunder: RSI was above MA, now at or below → OB
                crossunder = (prev_rsi > prev_ma) and (curr_rsi <= curr_ma)

                if not (crossover or crossunder):
                    continue

                signal = 'OS' if crossover else 'OB'
                gap    = round(curr_rsi - curr_ma, 2)
                name   = symbol.replace('/USDT', '').replace(':USDT', '')
                price_str   = f"{price:,.4f}" if price is not None else 'N/A'
                change_val  = change if change is not None else 0.0

                results.append({
                    'Name':      name,
                    'Symbol':    symbol,
                    'Timeframe': tf,
                    'Signal':    signal,
                    'RSI':       round(curr_rsi, 2),
                    'MA':        round(curr_ma, 2),
                    'Gap':       gap,          # RSI − MA at crossover point
                    'Prev_RSI':  round(prev_rsi, 2),
                    'Prev_MA':   round(prev_ma, 2),
                    'Price':     price_str,
                    'Change':    round(change_val, 2),
                    'RSI_Type':  rsi_type,
                    'RSI_Length':rsi_length,
                    'MA_Type':   ma_type,
                    'MA_Length': ma_length,
                })
                logging.info(
                    f"  OB/OS | {name} {tf} → {signal} | "
                    f"RSI {prev_rsi:.2f}→{curr_rsi:.2f} MA {prev_ma:.2f}→{curr_ma:.2f}"
                )
            except Exception as e:
                logging.debug(f"OB/OS calc error {symbol} {tf}: {e}")
    return results


async def run_ob_os_scan(timeframes: List[str], crypto_count: int = 50,
                         rsi_type: str = 'ALMA', rsi_length: int = 11,
                         ma_type: str = 'ALMA', ma_length: int = 9) -> List[dict]:
    """
    Main entry point for the OB/OS scanner.

    Parameters
    ----------
    timeframes   : UI timeframe labels e.g. ['15min', '1hr', '4hr']
    crypto_count : number of top Binance USDT pairs to scan
    rsi_type     : 'ALMA' (True RSI) or 'Standard' (Wilder)
    rsi_length   : RSI calculation period
    ma_type      : 'ALMA' or 'TEMA' — smoothing applied to True RSI
    ma_length    : period for the MA of RSI

    Signal logic
    ------------
    OS = True RSI crossover  MA  (crosses from below to above)
    OB = True RSI crossunder MA  (crosses from above to below)
    """
    logging.info(
        f"OB/OS Scan | TFs={timeframes} N={crypto_count} | "
        f"RSI={rsi_type}({rsi_length}) MA={ma_type}({ma_length})"
    )

    symbols_info = await _get_top_symbols(limit=crypto_count)
    if not symbols_info:
        logging.warning("OB/OS: no symbols fetched")
        return []

    semaphore = asyncio.Semaphore(8)
    tasks = [
        _scan_symbol(
            s['symbol'], timeframes,
            rsi_type, rsi_length, ma_type, ma_length,
            s.get('price'), s.get('change'), semaphore
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
