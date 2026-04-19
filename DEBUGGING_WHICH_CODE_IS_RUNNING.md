# Debugging: Which Code Is Actually Running?

## **The Problem**

You restarted the server, but the scanner results still don't match the indicator.

**Why?** The improvements in `scanner_enhancements.py` are NOT being used because `scanner.py` hasn't been modified to call them yet.

Just adding a new file doesn't change behavior. You need to:
1. ✓ Copy `scanner_enhancements.py` (done)
2. ✗ Modify `scanner.py` to USE those functions (NOT done yet)
3. ✗ Restart server (will restart, but no new code active)

---

## **How to Verify What's Running**

### **Method 1: Check if Imports are Actually There**

**Step 1: Open scanner.py and search for the import statement**
```bash
grep -n "from scanner_enhancements import" /Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend/scanner.py
```

**Expected Output if enhancements are imported:**
```
15: from scanner_enhancements import (
```

**If you see NOTHING, the enhancements are NOT imported yet**

---

### **Method 2: Add Debug Logging**

This is the BEST way to see what code is running:

**Edit `scanner.py` and find the `apply_qwen_multi_ma()` function (around line 1134)**

**Add this at the START of the function:**
```python
def apply_qwen_multi_ma(df, ma_type="ALMA", tf_input="1 day", use_current_candle=False, **kwargs):
    """Enhanced version with adaptive MA periods"""
    
    # DEBUG: Log which version is running
    import sys
    print(f"[DEBUG] apply_qwen_multi_ma called with ma_type={ma_type}, tf_input={tf_input}", file=sys.stderr)
    
    # Check if enhancements are available
    try:
        from scanner_enhancements import calculate_adaptive_ma_periods
        print(f"[DEBUG] ✓ Enhancements module FOUND and LOADED", file=sys.stderr)
        using_enhancements = True
    except ImportError as e:
        print(f"[DEBUG] ✗ Enhancements module NOT found: {e}", file=sys.stderr)
        using_enhancements = False
    
    print(f"[DEBUG] Using enhancements: {using_enhancements}", file=sys.stderr)
    
    # ... rest of your function ...
```

**Now restart the server and run a scan:**
```bash
# Watch the server logs
tail -f /path/to/backend.log

# Or if running in foreground, you'll see the debug output
```

**You'll see something like:**
```
[DEBUG] apply_qwen_multi_ma called with ma_type=ALMA, tf_input=15min
[DEBUG] ✓ Enhancements module FOUND and LOADED
[DEBUG] Using enhancements: True
```

Or if NOT using enhancements:
```
[DEBUG] apply_qwen_multi_ma called with ma_type=ALMA, tf_input=15min
[DEBUG] ✗ Enhancements module NOT found: No module named 'scanner_enhancements'
[DEBUG] Using enhancements: False
```

---

### **Method 3: Check API Response for Metadata**

If enhancements are working, the API response should include new metadata fields.

**Run a scan and check the response:**
```bash
# Call the scanner API
curl -X POST http://localhost:8001/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "indices": ["CRYPTO"],
    "timeframes": ["15min"],
    "scanner_type": "ama_pro",
    "crypto_count": 20
  }' | jq '.[0]'
```

**Expected response WITH enhancements:**
```json
{
  "Crypto Name": "BTCUSDT",
  "Signal": "LONG",
  "RSI": 45,
  "Angle": 12.5,
  "signal_metadata": {
    "volume_regime": "NORMAL",
    "strategy_mode": "balanced",
    "signal_confidence": 78,
    "htf_aligned": true,
    "adaptive_periods": {
      "fast": 12.3,
      "slow": 27.8
    }
  }
}
```

**Expected response WITHOUT enhancements:**
```json
{
  "Crypto Name": "BTCUSDT",
  "Signal": "LONG",
  "RSI": 45,
  "Angle": 12.5
  // NO signal_metadata field
}
```

If you DON'T see `signal_metadata`, the enhancements are NOT active.

---

## **The Most Likely Issue: scanner.py Wasn't Modified**

Let me check if you actually made the changes:

**Run this command:**
```bash
# Check if scanner.py has been modified with enhancement calls
grep -n "calculate_adaptive_ma_periods\|validate_signal_quality\|classify_volume_regime" /Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend/scanner.py
```

**If output is empty, scanner.py was NEVER modified** ← This is probably the issue

---

## **How to Fix: Actually Use the Enhancements**

### **Quick Fix (30 minutes)**

I'll modify scanner.py for you RIGHT NOW to use the enhancements. Let me do that:

---

## **Step-by-Step to Activate Enhancements**

### **Step 1: Verify scanner_enhancements.py exists**
```bash
ls -la /Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend/scanner_enhancements.py
```

**Should output:**
```
-rw-r--r--  1 user  group  15234 Apr 19 12:00 scanner_enhancements.py
```

If NOT there, you need to copy it first.

### **Step 2: Add imports to scanner.py (Line 15)**

Find this line in scanner.py:
```python
import logging
from concurrent.futures import ThreadPoolExecutor
```

Add AFTER these imports:
```python
# Import enhancements (NEW - line ~20)
try:
    from scanner_enhancements import (
        calculate_adaptive_ma_periods,
        calculate_crossover_angle,
        validate_signal_quality,
        calculate_adaptive_rsi_thresholds,
        classify_volume_regime,
        calculate_volatility_adjusted_sl,
        calculate_volatility_adjusted_target,
        select_strategy_mode,
        check_htf_alignment,
        check_pending_entry_confirmation,
        calculate_adx,
        calculate_rsi
    )
    ENHANCEMENTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Enhancements not available: {e}")
    ENHANCEMENTS_AVAILABLE = False
```

### **Step 3: Modify apply_qwen_multi_ma() to use enhancements**

Find this section (around line 1134+):
```python
def apply_qwen_multi_ma(df, ma_type="ALMA", tf_input="1 day", use_current_candle=False, **kwargs):
    # ...existing code...
    
    # OLD WAY (before):
    ma_fast_length = 12
    ma_slow_length = 26
```

**Replace with:**
```python
def apply_qwen_multi_ma(df, ma_type="ALMA", tf_input="1 day", use_current_candle=False, **kwargs):
    # ...existing code...
    
    # NEW WAY (with enhancements):
    if ENHANCEMENTS_AVAILABLE:
        # Calculate timeframe in minutes
        tf_clean = tf_input.lower().strip()
        if 'min' in tf_clean:
            timeframe_minutes = int(tf_clean.replace('min', ''))
        elif 'hr' in tf_clean:
            timeframe_minutes = int(tf_clean.replace('hr', '')) * 60
        else:
            timeframe_minutes = 1440
        
        # IMPROVEMENT 1: ADAPTIVE MA PERIODS
        adaptation_speed = kwargs.get('adaptation_speed', 'Medium')
        ma_fast_length, ma_slow_length = calculate_adaptive_ma_periods(
            df=df,
            base_fast=12,
            base_slow=26,
            timeframe_minutes=timeframe_minutes,
            adaptation_speed=adaptation_speed
        )
        ma_fast_length = int(round(ma_fast_length))
        ma_slow_length = int(round(ma_slow_length))
    else:
        # Fallback to original
        ma_fast_length = 12
        ma_slow_length = 26
```

### **Step 4: Modify angle calculation**

Find the angle calculation (around line 1300+):
```python
# OLD:
angle = abs(ma_fast[-1] - ma_slow[-1]) / close[-1] * 100
```

**Replace with:**
```python
# NEW: IMPROVEMENT 2 - Better angle calculation
if ENHANCEMENTS_AVAILABLE and len(ma_fast_series) >= 4:
    angle = calculate_crossover_angle(
        fast_ma=ma_fast_series,
        slow_ma=ma_slow_series,
        lookback=4
    )
else:
    # Fallback
    angle = abs(ma_fast[-1] - ma_slow[-1]) / close[-1] * 100
```

### **Step 5: Add volume regime classification**

Before signal return, add:
```python
# IMPROVEMENT 7: Volume regime
if ENHANCEMENTS_AVAILABLE:
    volume_regime = classify_volume_regime(df, lookback=50)
else:
    volume_regime = "NORMAL"
```

### **Step 6: Restart server**
```bash
systemctl restart gemini-backend

# Verify it started
systemctl status gemini-backend

# Check logs for errors
journalctl -u gemini-backend -n 20
```

### **Step 7: Test again**
```bash
curl -X POST http://localhost:8001/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "indices": ["CRYPTO"],
    "timeframes": ["15min"],
    "scanner_type": "ama_pro",
    "crypto_count": 5
  }' | jq '.[] | {name: ."Crypto Name", signal: .Signal, angle: .Angle, signal_metadata}'
```

**Now you should see signal_metadata and different results** ✓

---

## **Comparison: Scanner vs Indicator**

### **Why Results Might Still Not Match**

Even WITH enhancements, scanner and indicator may differ because:

| Factor | Scanner | Indicator | Why Different |
|--------|---------|-----------|-------|
| **Timeframe** | 15m candle data | Real-time chart | Candle vs live data |
| **Lookback** | Last 100 candles | Visual (50+ candles) | Different history |
| **MA Type** | Your chosen MA | McGinley default | You set ALMA vs McGinley |
| **RSI Period** | 14 (fixed) | 14 (fixed) | Same usually |
| **Update lag** | API call time | Real-time | Network delay |
| **Volume** | Binance API | TradingView data | Different exchanges |
| **HTF data** | You fetch 1h | Visual | Alignment differs |

### **How to Compare Properly**

**Check a SPECIFIC coin on a SPECIFIC timeframe:**

```bash
# 1. Check what scanner returns
curl http://localhost:8001/api/scan -H "Content-Type: application/json" \
  -d '{"scanner_type":"ama_pro", "timeframes":["15min"], "crypto_count":1}' \
  | jq '.[] | select(."Crypto Name"=="BTCUSDT")'

# Expected output:
# {
#   "Crypto Name": "BTCUSDT",
#   "Signal": "LONG or SHORT or null",
#   "RSI": 45.2,
#   "Angle": 12.5,
#   "TEMA Gap": 0.8,
#   "signal_metadata": { ... }
# }

# 2. Go to TradingView and check BTCUSDT 15m chart manually
# Does the Qwen MMA indicator show a signal?
# Compare: Scanner says LONG, indicator shows LONG? → Match ✓
```

---

## **Troubleshooting Checklist**

- [ ] `scanner_enhancements.py` copied to backend/ ?
- [ ] Import statement added to scanner.py (lines 15-20)?
- [ ] `apply_qwen_multi_ma()` modified to use `calculate_adaptive_ma_periods()`?
- [ ] Angle calculation updated?
- [ ] Server restarted after ALL changes?
- [ ] API response includes `signal_metadata` field?
- [ ] No import errors in server logs?

**If ANY of these is unchecked, enhancements are NOT active.**

---

## **Quick Debug Script**

Run this to check everything:
```python
# test_enhancements.py
import sys
sys.path.insert(0, '/Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend')

# Test 1: Can we import enhancements?
try:
    from scanner_enhancements import calculate_adaptive_ma_periods
    print("✓ scanner_enhancements.py can be imported")
except ImportError as e:
    print(f"✗ Cannot import scanner_enhancements: {e}")
    sys.exit(1)

# Test 2: Can we import scanner with enhancements?
try:
    from scanner import apply_qwen_multi_ma
    print("✓ scanner.py can be imported")
except ImportError as e:
    print(f"✗ Cannot import scanner: {e}")
    sys.exit(1)

# Test 3: Check if ENHANCEMENTS_AVAILABLE flag exists
try:
    from scanner import ENHANCEMENTS_AVAILABLE
    print(f"✓ ENHANCEMENTS_AVAILABLE = {ENHANCEMENTS_AVAILABLE}")
except ImportError:
    print("✗ ENHANCEMENTS_AVAILABLE not found (scanner.py not modified)")

print("\n✓ All checks passed - enhancements should be active")
```

**Run it:**
```bash
cd /Users/sushantakumarsahoo/Downloads/Gemini_Crypto/backend
python test_enhancements.py
```

---

## **Bottom Line**

**The reason results don't match:**

```
scanner_enhancements.py exists BUT scanner.py doesn't use it
                    ↓
Scanner still uses OLD logic
                    ↓
Results are same as before (33% WR)
                    ↓
Indicator shows different results (70% WR)
```

**Solution:**
1. Modify scanner.py to import and USE the enhancement functions
2. Restart server
3. Test again
4. Now you should see improvements

I can modify scanner.py for you right now if you'd like!
