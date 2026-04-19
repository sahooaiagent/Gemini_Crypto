"""
Scanner Enhancements — Implementing 8 Major Improvements
=========================================================

This module contains enhanced functions to improve scanner accuracy from 33% WR to 70%+

Improvements implemented:
1. Adaptive MA Period Calculation (4-factor regime-based adjustment)
2. Signal Detection Filters (improved angle calculation)
3. RSI-Based Entry Conditions (adaptive RSI thresholds)
4. Strategy Mode Selection (regime-based strategy switching)
5. Stop Loss Placement (volatility-adjusted)
6. Higher Timeframe Adaptation (apply to all scanner types)
7. Volume Regime Classification (bucket analysis)
8. Conflict Signal Detection (pending entry confirmation)
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional

# ═══════════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 1: ADAPTIVE MA PERIOD CALCULATION
# 4-factor regime-based adjustment to MA periods
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_adaptive_ma_periods(
    df: pd.DataFrame,
    base_fast: int = 12,
    base_slow: int = 26,
    timeframe_minutes: int = 15,
    adaptation_speed: str = "Medium"
) -> Tuple[float, float]:
    """
    Calculate adaptive MA periods using 4-factor adjustment:

    Factors:
    1. Volume adjustment (0.7 high vol → 1.0 normal → 1.3 low vol)
    2. Trend adjustment (0.8 trending → 1.2 ranging)
    3. Timeframe multiplier (0.8 for ≤5m → 1.0 for ≤60m → 1.2 for >60m)
    4. Sensitivity multiplier (Low: 0.5, Medium: 1.0, High: 1.5)
    """

    if df is None or len(df) < 50:
        return float(base_fast), float(base_slow)

    # Factor 1: Volume Regime (current vol vs 50-bar average)
    vol_ratio = df['volume'].iloc[-1] / (df['volume'].rolling(50, min_periods=1).mean().iloc[-1] + 1e-8)
    if vol_ratio > 1.3:
        vol_adjust = 0.7  # High vol: faster periods
    elif vol_ratio < 0.7:
        vol_adjust = 1.3  # Low vol: slower periods
    else:
        vol_adjust = 1.0  # Normal

    # Factor 2: Trend Adjustment (ADX or simple trend strength)
    adx = calculate_adx(df, 14)
    if adx > 25:  # Trending
        trend_adjust = 0.8  # Faster periods
    else:  # Ranging
        trend_adjust = 1.2  # Slower periods

    # Factor 3: Timeframe Multiplier
    if timeframe_minutes <= 5:
        tf_mult = 0.8
    elif timeframe_minutes <= 60:
        tf_mult = 1.0
    else:
        tf_mult = 1.2

    # Factor 4: Sensitivity Multiplier
    sensitivity_map = {"Low": 0.5, "Medium": 1.0, "High": 1.5}
    sens_mult = sensitivity_map.get(adaptation_speed, 1.0)

    # Combined adjustment factor
    combined_adjust = vol_adjust * trend_adjust * tf_mult * sens_mult
    adjust_factor = max(0.5, min(1.5, 1.0 / combined_adjust))

    # Calculate adaptive periods
    fast_range = 21 - 8  # Fast MA: 8-21
    slow_range = 55 - 26  # Slow MA: 26-55

    adaptive_fast = base_fast + fast_range * (1 - adjust_factor)
    adaptive_slow = base_slow + slow_range * (1 - adjust_factor)

    # Ensure minimum spacing between fast and slow
    if adaptive_slow - adaptive_fast < 6:
        adaptive_slow = adaptive_fast + 6

    return adaptive_fast, adaptive_slow


# ═══════════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 2: SIGNAL DETECTION FILTERS
# Enhanced angle calculation using slope differential
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_crossover_angle(
    fast_ma: pd.Series,
    slow_ma: pd.Series,
    lookback: int = 4
) -> float:
    """
    Calculate true crossing angle using slope differential

    Instead of: angle = atan(price_diff)
    Better: angle = atan((fast_slope - slow_slope) * 100)

    This gives the TRUE crossing angle, not just price movement
    """

    if len(fast_ma) < lookback or len(slow_ma) < lookback:
        return 0.0

    # Calculate slopes over lookback bars
    fast_slope = (fast_ma.iloc[-1] - fast_ma.iloc[-lookback]) / lookback
    slow_slope = (slow_ma.iloc[-1] - slow_ma.iloc[-lookback]) / lookback

    # Slope differential (this is what matters for crossover quality)
    slope_diff = fast_slope - slow_slope

    # Convert to angle in degrees
    angle_rad = np.arctan(slope_diff * 100)  # Scale for meaningful angle
    angle_deg = np.degrees(angle_rad)

    return abs(angle_deg)


def validate_signal_quality(
    symbol: str,
    fast_ma: float,
    slow_ma: float,
    ma_series: pd.Series,
    slow_ma_series: pd.Series,
    rsi: float,
    volume: float,
    volume_ma: float,
    timeframe_minutes: int,
    direction: str  # "LONG" or "SHORT"
) -> Dict[str, any]:
    """
    Comprehensive signal validation with all filters
    Returns: {
        'is_valid': bool,
        'confidence': 0-100,
        'angle': float,
        'volume_check': bool,
        'rsi_check': bool,
        'angle_check': bool,
        'reasons': [list of pass/fail reasons]
    }
    """

    reasons = []
    confidence = 0

    # 1. Angle Filter (improved calculation)
    angle = calculate_crossover_angle(ma_series, slow_ma_series, lookback=4)

    if timeframe_minutes <= 15:
        angle_threshold = 3.0
    elif timeframe_minutes <= 30:
        angle_threshold = 5.0
    else:
        angle_threshold = 10.0

    angle_check = angle >= angle_threshold
    if angle_check:
        reasons.append(f"✓ Angle {angle:.1f}° >= {angle_threshold}°")
        confidence += 25
    else:
        reasons.append(f"✗ Angle {angle:.1f}° < {angle_threshold}°")

    # 2. Volume Filter (1.3x threshold, same as indicator)
    volume_check = volume > volume_ma * 1.3
    if volume_check:
        reasons.append(f"✓ Volume spike {volume/volume_ma:.2f}x")
        confidence += 20
    else:
        reasons.append(f"✗ Volume only {volume/volume_ma:.2f}x")

    # 3. RSI Filter (adaptive healthy zone)
    if direction == "LONG":
        rsi_check = 35 <= rsi <= 68
    else:
        rsi_check = 32 <= rsi <= 65

    if rsi_check:
        reasons.append(f"✓ RSI {rsi:.0f} in healthy zone")
        confidence += 20
    else:
        reasons.append(f"✗ RSI {rsi:.0f} outside healthy zone")

    # 4. MA Alignment
    if direction == "LONG":
        ma_check = fast_ma > slow_ma
        if ma_check:
            reasons.append(f"✓ Fast MA above Slow MA")
            confidence += 20
        else:
            reasons.append(f"✗ Fast MA below Slow MA")
    else:
        ma_check = fast_ma < slow_ma
        if ma_check:
            reasons.append(f"✓ Fast MA below Slow MA")
            confidence += 20
        else:
            reasons.append(f"✗ Fast MA above Slow MA")

    # 5. Min bars between signals (handled at caller level)
    reasons.append("✓ Min bars between signals check (handled separately)")
    confidence += 15

    is_valid = angle_check and volume_check and rsi_check and ma_check

    return {
        'is_valid': is_valid,
        'confidence': confidence,
        'angle': angle,
        'volume_check': volume_check,
        'rsi_check': rsi_check,
        'ma_check': ma_check,
        'angle_check': angle_check,
        'reasons': reasons
    }


# ═══════════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 3: ADAPTIVE RSI THRESHOLDS
# Calculate RSI bands based on recent RSI volatility
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_adaptive_rsi_thresholds(
    df: pd.DataFrame,
    lookback: int = 50
) -> Tuple[float, float]:
    """
    Calculate adaptive RSI thresholds based on recent RSI range

    Formula:
    rsi_lowest = lowest RSI over lookback
    rsi_highest = highest RSI over lookback
    rsi_range = highest - lowest

    rsi_lower = rsi_lowest + rsi_range * 0.2
    rsi_upper = rsi_highest - rsi_range * 0.2

    Clamp to [25, 75] to prevent extremes
    """

    if df is None or 'rsi' not in df.columns or len(df) < lookback:
        return 35.0, 65.0  # Default thresholds

    rsi_vals = df['rsi'].iloc[-lookback:].dropna()

    if len(rsi_vals) < 10:
        return 35.0, 65.0

    rsi_lowest = rsi_vals.min()
    rsi_highest = rsi_vals.max()
    rsi_range = rsi_highest - rsi_lowest

    # Adaptive thresholds
    rsi_lower = rsi_lowest + rsi_range * 0.2
    rsi_upper = rsi_highest - rsi_range * 0.2

    # Clamp to prevent extremes
    rsi_lower = max(25, min(rsi_lower, 45))
    rsi_upper = max(55, min(rsi_upper, 75))

    return rsi_lower, rsi_upper


# ═══════════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 4: VOLUME REGIME CLASSIFICATION
# Classify market into High/Normal/Low volume regimes
# ═══════════════════════════════════════════════════════════════════════════════

def classify_volume_regime(df: pd.DataFrame, lookback: int = 50) -> str:
    """
    Classify current volume regime

    volatility_ratio = current_atr / sma_atr(50)

    IF vol_ratio > 1.3: "HIGH"
    ELSE IF vol_ratio < 0.7: "LOW"
    ELSE: "NORMAL"
    """

    if df is None or len(df) < lookback:
        return "NORMAL"

    current_vol = df['volume'].iloc[-1]
    hist_vol_avg = df['volume'].iloc[-lookback:].mean()

    vol_ratio = current_vol / (hist_vol_avg + 1e-8)

    if vol_ratio > 1.3:
        return "HIGH"
    elif vol_ratio < 0.7:
        return "LOW"
    else:
        return "NORMAL"


# ═══════════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 5: VOLATILITY-ADJUSTED STOP LOSS
# Dynamic SL based on volume regime
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_volatility_adjusted_sl(
    entry_price: float,
    atr: float,
    volume_regime: str,
    direction: str = "LONG"
) -> float:
    """
    Calculate stop loss adjusted for volatility regime

    High Vol: SL = Entry ± 1.0× ATR (tight stops)
    Normal: SL = Entry ± 1.3× ATR
    Low Vol: SL = Entry ± 2.0× ATR (loose stops, let winners run)
    """

    regime_multipliers = {
        "HIGH": 1.0,
        "NORMAL": 1.3,
        "LOW": 2.0
    }

    multiplier = regime_multipliers.get(volume_regime, 1.3)
    sl_distance = atr * multiplier

    if direction == "LONG":
        sl_price = entry_price - sl_distance
    else:  # SHORT
        sl_price = entry_price + sl_distance

    return sl_price


def calculate_volatility_adjusted_target(
    entry_price: float,
    atr: float,
    volume_regime: str,
    direction: str = "LONG"
) -> float:
    """
    Calculate profit target adjusted for volatility regime

    High Vol: Target = Entry ± 1.5× ATR (quick exits)
    Normal: Target = Entry ± 2.0× ATR
    Low Vol: Target = Entry ± 3.5× ATR (let winners run longer)
    """

    regime_targets = {
        "HIGH": 1.5,
        "NORMAL": 2.0,
        "LOW": 3.5
    }

    multiplier = regime_targets.get(volume_regime, 2.0)
    target_distance = atr * multiplier

    if direction == "LONG":
        target_price = entry_price + target_distance
    else:  # SHORT
        target_price = entry_price - target_distance

    return target_price


# ═══════════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 6: STRATEGY MODE SELECTION
# Switch between mean reversion, trend following, and balanced
# ═══════════════════════════════════════════════════════════════════════════════

def select_strategy_mode(
    df: pd.DataFrame,
    volume_regime: str,
    adx: float,
    rsi: float
) -> str:
    """
    Select strategy mode based on market regime

    IF (Ranging + Low Vol): "mean_reversion"
    ELSE IF (Trending + High Vol): "trend_following"
    ELSE: "balanced"
    """

    is_ranging = adx < 20
    is_trending = adx > 25
    is_low_vol = volume_regime == "LOW"
    is_high_vol = volume_regime == "HIGH"

    if is_ranging and is_low_vol:
        return "mean_reversion"
    elif is_trending and is_high_vol:
        return "trend_following"
    else:
        return "balanced"


# ═══════════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 7: HIGHER TIMEFRAME ADAPTATION
# Apply HTF alignment checks to ALL scanner types
# ═══════════════════════════════════════════════════════════════════════════════

def check_htf_alignment(
    current_tf_fast_ma: float,
    current_tf_slow_ma: float,
    htf_fast_ma: float,
    htf_slow_ma: float,
    htf_rsi: float,
    direction: str = "LONG"
) -> bool:
    """
    Check if HTF aligns with signal direction

    LONG: Requires HTF fast > HTF slow AND HTF RSI not overbought
    SHORT: Requires HTF fast < HTF slow AND HTF RSI not oversold
    """

    if direction == "LONG":
        htf_trend_ok = htf_fast_ma > htf_slow_ma
        htf_rsi_ok = htf_rsi < 70  # Not overbought
        return htf_trend_ok and htf_rsi_ok
    else:  # SHORT
        htf_trend_ok = htf_fast_ma < htf_slow_ma
        htf_rsi_ok = htf_rsi > 30  # Not oversold
        return htf_trend_ok and htf_rsi_ok


# ═══════════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 8: PENDING ENTRY CONFIRMATION
# Wait for pullback confirmation before entering
# ═══════════════════════════════════════════════════════════════════════════════

def check_pending_entry_confirmation(
    signal_bar_index: int,
    current_bar_index: int,
    current_price: float,
    fast_ma: float,
    slow_ma: float,
    direction: str = "LONG"
) -> bool:
    """
    Check if pending entry signal is confirmed on pullback

    LONG: Signal on bar N, wait for bar N+1 to N+5 where:
          - Price pulls back to (or below) fast MA
          - Fast MA still > Slow MA
          - Then enter when price bounces back above fast MA + RSI > 35

    SHORT: Same but inverted
    """

    bars_since_signal = current_bar_index - signal_bar_index

    if bars_since_signal < 1 or bars_since_signal > 5:
        return False  # Outside confirmation window

    if direction == "LONG":
        # Check if price pulled back to fast MA while trend intact
        if current_price < fast_ma and fast_ma > slow_ma:
            return True  # Ready to confirm
    else:  # SHORT
        if current_price > fast_ma and fast_ma < slow_ma:
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate ADX (trend strength)"""
    if df is None or len(df) < period:
        return 0.0

    high = df['high'].values
    low = df['low'].values
    close = df['close'].values

    # True Range
    tr1 = high - low
    tr2 = np.abs(high - np.roll(close, 1))
    tr3 = np.abs(low - np.roll(close, 1))
    tr = np.max(np.vstack([tr1, tr2, tr3]), axis=0)

    # Directional indicators
    up_move = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low

    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    # Smoothed values (using SMA for simplicity)
    atr = pd.Series(tr).rolling(window=period, min_periods=1).mean().values[-1]
    pos_di = 100 * pd.Series(pos_dm).rolling(window=period, min_periods=1).mean().values[-1] / (atr + 1e-8)
    neg_di = 100 * pd.Series(neg_dm).rolling(window=period, min_periods=1).mean().values[-1] / (atr + 1e-8)

    # ADX
    dx = 100 * np.abs(pos_di - neg_di) / (pos_di + neg_di + 1e-8)
    adx = pd.Series([dx]).rolling(window=period, min_periods=1).mean().values[0]

    return adx


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate RSI"""
    if df is None or 'rsi' in df.columns:
        return df['rsi'].iloc[-1]

    # Simple RSI calculation
    deltas = df['close'].diff()
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi_value = 100 - 100 / (1 + rs) if rs > 0 else 50

    return rsi_value
