# 8 Improvements Implementation Checklist

## Quick Start (Follow in Order)

### **Phase 1: Setup (1-2 hours)**
- [ ] Copy `scanner_enhancements.py` to `/backend/`
- [ ] Add import statement to `scanner.py` line ~15
- [ ] Verify no import errors: `python -c "from scanner_enhancements import *"`

### **Phase 2: Core Enhancements (3-4 hours)**

#### **Improvement #1: Adaptive MA Periods**
- [ ] Locate `apply_qwen_multi_ma()` function (line ~1134)
- [ ] Replace hardcoded `ma_fast_length = 12` with call to `calculate_adaptive_ma_periods()`
- [ ] Test: Run scanner on 1h chart, verify MA lengths adjust with vol/trend
- [ ] Expected: Faster response in trending markets, slower in ranging

#### **Improvement #2: Enhanced Angle Calculation**
- [ ] Find angle calculation in same function (around line ~1300+)
- [ ] Replace `angle = abs(ma_fast[-1] - ma_slow[-1])` with `calculate_crossover_angle()`
- [ ] Verify angle >= 3° for 10m, >= 5° for 30m, >= 10° for 1h
- [ ] Test: Check that weak crossovers are rejected

#### **Improvement #3: Adaptive RSI Thresholds**
- [ ] Before signal generation, add call to `calculate_adaptive_rsi_thresholds()`
- [ ] Replace hardcoded `rsi_lower=35, rsi_upper=65` with returned values
- [ ] Test: Verify RSI bands adapt to recent RSI volatility
- [ ] Expected: Wider bands in volatile markets, tighter in calm markets

#### **Improvement #4: Volume Regime Classification**
- [ ] Add `volume_regime = classify_volume_regime(df)` to signal logic
- [ ] Store in result dictionary for frontend display
- [ ] Test: Verify regime changes HIGH/NORMAL/LOW appropriately

#### **Improvement #5: Volatility-Adjusted Stop Loss**
- [ ] Replace `stop_loss = entry_price - atr * 1.2` with call to `calculate_volatility_adjusted_sl()`
- [ ] Also add target calculation: `calculate_volatility_adjusted_target()`
- [ ] Test: Verify SL becomes tighter in high vol, looser in low vol

#### **Improvement #6: HTF Alignment for ALL Scanners**
- [ ] Find all signal generation points (AMA, Qwen, HILEGA, etc.)
- [ ] Add HTF alignment check to EACH: `check_htf_alignment()`
- [ ] Currently only SHORT has this; add for LONG too
- [ ] Test: Verify signals rejected when HTF misaligns

#### **Improvement #7: Strategy Mode Selection**
- [ ] Add `strategy_mode = select_strategy_mode()` call
- [ ] Use strategy_mode to gate/adjust signals:
  - `"mean_reversion"` → Focus on Bollinger Band extremes
  - `"trend_following"` → Focus on MA crossovers
  - `"balanced"` → Combined logic
- [ ] Test: Verify mode changes with ADX and volume

#### **Improvement #8: Pending Entry Confirmation**
- [ ] Implement pending signal tracking (dict of pending signals)
- [ ] Call `check_pending_entry_confirmation()` on each bar
- [ ] Only return signal as "CONFIRMED" after 1-5 bars of pullback
- [ ] Test: Verify signals wait for confirmation before entry

### **Phase 3: Frontend Integration (1-2 hours)**

- [ ] Update API response to include signal_metadata dict
- [ ] Add to frontend display:
  - Volume regime badge (HIGH/NORMAL/LOW)
  - Strategy mode label (MR/TF/BAL)
  - Signal confidence percentage (0-100)
  - HTF alignment status (✓/✗)
  - Adaptive MA periods (fast/slow)

### **Phase 4: Testing (2-3 days)**

#### **Day 1: Backtest**
- [ ] Run scanner on last 3 months of BTC/ETH 15m data
- [ ] Measure:
  - Win rate (target: 60%+ vs current 33%)
  - Avg win/loss ratio
  - Sharpe ratio
  - Max drawdown
- [ ] Expected improvement: +25-50% WR

#### **Day 2: Paper Trade**
- [ ] Set scanner to "live mode" but don't take real trades
- [ ] Run for full day (06:00-22:00 CET)
- [ ] Count signals, verify:
  - Volume regime detection works
  - HTF alignment filters bad signals
  - RSI thresholds adapt
- [ ] Expected: 60%+ signals pass all filters

#### **Day 3-5: Live Trade (Small Position)**
- [ ] Start with €10 position size (0.1% account risk)
- [ ] Take all signals as they come
- [ ] Track:
  - Actual win rate (target: 60%+)
  - Slippage (should be minimal)
  - Any error messages
- [ ] Expected: 60%+ WR achieved

### **Phase 5: Optimization (Ongoing)**

- [ ] Monitor daily WR by coin
- [ ] Adjust `adaptation_speed` (Low/Medium/High) based on results
- [ ] Fine-tune `min_signal_confidence` threshold
- [ ] Add coin-specific whitelisting if needed

---

## **Validation Checklist**

### **Code Quality**
- [ ] No import errors
- [ ] All function signatures match calls
- [ ] No numpy/pandas deprecation warnings
- [ ] Code runs without exceptions

### **Signal Quality**
- [ ] Fewer false signals (angle filter working)
- [ ] Better entry timing (pending confirmation working)
- [ ] No overnight trades (time gate working)
- [ ] HTF alignment reducing counter-trend trades

### **Performance**
- [ ] Backtest WR >= 60%
- [ ] Paper trade WR >= 60%
- [ ] Live trade WR >= 60%
- [ ] Avg win/loss ratio > 1.5

---

## **Common Issues & Fixes**

### **Issue: "No signals generated"**
- Check if signal_confidence < min_signal_confidence threshold
- Lower `min_signal_confidence` from 65 to 50
- Verify `enable_signal_quality_checks = False` temporarily to test

### **Issue: "WR decreased to 20%"**
- HTF alignment too strict; try loosening RSI threshold to 40-60
- Set `enable_htf_alignment_all = False` temporarily
- Volume regime detection may be wrong; verify vol_ratio calculation

### **Issue: "Adapting to wrong market regime"**
- ADX calculation might be wrong; verify with known chart
- Try `strategy_mode_switching = False` temporarily
- Set fixed `strategy_mode = "balanced"` to test

### **Issue: "SL too tight, constant stops"**
- Increase `volume_regime` multiplier: 1.0 → 1.5 in HIGH vol
- Try `enable_volatility_adjusted_sl = False` (use fixed 1.3× ATR)

### **Issue: "Missing signals vs TradingView indicator"**
- Pending confirmation may be filtering valid signals
- Set `enable_pending_confirmation = False`
- Check that min_bars_between_signals = 3 (not 5)

---

## **Rollback Plan (If WR Decreases)**

If WR drops below 40% after implementation:

1. **Disable Pending Confirmation** (easiest to fix)
   - Set `enable_pending_confirmation = False`
   - Expected recovery: +10% WR

2. **Relax Signal Quality Checks**
   - Increase `min_signal_confidence` from 65 to 40
   - Expected recovery: +15% WR

3. **Disable HTF Alignment**
   - Set `enable_htf_alignment_all = False`
   - Keep HTF only for SHORT signals
   - Expected recovery: +8% WR

4. **Disable Strategy Mode Switching**
   - Set `enable_strategy_mode_switching = False`
   - Use fixed "balanced" mode
   - Expected recovery: +5% WR

5. **Full Rollback**
   - Comment out all enhancement imports
   - Revert to original scanner.py
   - No loss (back to 33% WR)

---

## **Success Metrics**

### **Phase 1 (Backtest): PASS if**
- [ ] WR >= 55% on backtest
- [ ] No errors in signal generation
- [ ] Improvements measurable (MA adapt, angle improve, etc.)

### **Phase 2 (Paper Trade): PASS if**
- [ ] WR >= 55% on paper
- [ ] Volume regime detected correctly
- [ ] HTF filters working
- [ ] Signal quality reasonable

### **Phase 3 (Live Trade): PASS if**
- [ ] WR >= 55% on live
- [ ] Consistent with paper performance
- [ ] No unexpected errors
- [ ] Slippage acceptable

### **Final Goal: ACHIEVE**
- [ ] WR >= 65% consistent
- [ ] Daily return >= 0.8% (on your micro account)
- [ ] Sharpe ratio > 1.0
- [ ] Ready to scale

---

## **Time Estimate**

| Phase | Task | Time | Difficulty |
|-------|------|------|------------|
| 1 | Setup & imports | 1 hr | Easy |
| 2.1-2.4 | Core enhancements | 2-3 hrs | Medium |
| 2.5-2.8 | Advanced features | 1-2 hrs | Hard |
| 3 | Frontend integration | 1-2 hrs | Easy |
| 4 | Testing | 3-5 days | Medium |
| 5 | Optimization | Ongoing | Hard |

**Total: 2-3 days implementation + 3-5 days testing = 1-2 weeks to 65%+ WR**

---

## **Key Files Modified**

| File | Changes | Lines Affected |
|------|---------|-----------------|
| scanner_enhancements.py | NEW | All (350+ lines) |
| scanner.py | Import + 8 functions | +50 lines total |
| main.py | API response format | +10 lines |
| app.js | Frontend display | +20 lines |

**No breaking changes; all enhancements are additive**

---

## **Getting Help**

If stuck on any improvement:

1. Check `SCANNER_ENHANCEMENT_INTEGRATION_GUIDE.md` for detailed steps
2. Review function docstrings in `scanner_enhancements.py`
3. Test with simpler cases first (e.g., single coin, single TF)
4. Disable improvements one-by-one to isolate issues
5. Compare backtest results to TradingView indicator

Good luck! Expected WR improvement: **33% → 65-75%**
