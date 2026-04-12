import logging
import datetime
import time
import statistics
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Union
import os
import sys

# Import scanner logic
import scanner

app = FastAPI(title="Gemini Scanner Enterprise API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup basic file logging that frontend can read
log_file = "scanner_runtime.log"
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Also log to console
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)

# Store latest scan results in memory for fast access
latest_scan = {
    "results": [],
    "hilega_results": [],
    "cross_results": [],
    "conflict_results": [],
    "gap_results": [],
    "scan_time": None,
    "duration": None
}

class ScanRequest(BaseModel):
    indices: List[str]
    timeframes: List[str]
    adaptation_speed: Optional[str] = "Medium"
    min_bars_between: Optional[int] = 3
    crypto_count: Optional[int] = 20
    scanner_type: Optional[Union[str, List[str]]] = "ama_pro"  # Single: 'ama_pro', 'qwen', 'both', etc. OR Multiple: ['ama_pro', 'ama_pro_now']
    ma_type: Optional[str] = "ALMA"  # Moving Average Type: 'ALMA', 'JMA', 'T3', 'McGinley', 'KAMA'
    auto_ma_type: Optional[bool] = True  # Auto-select MA type based on asset+timeframe (overrides ma_type)
    enable_regime_filter: Optional[bool] = True  # Advanced Filter: Regime Detection
    enable_volume_filter: Optional[bool] = False  # Advanced Filter: Volume Confirmation
    enable_angle_filter: Optional[bool] = True  # Advanced Filter: Angle Threshold
    hilega_buy_rsi: Optional[int] = 10  # HILEGA BUY RSI threshold
    hilega_sell_rsi: Optional[int] = 90  # HILEGA SELL RSI threshold
    hilega_rsi_mode: Optional[str] = "ALMA Fixed"  # HILEGA RSI Mode: 'ALMA Fixed', 'ALMA', 'RMA'
    alma_fixed_rsi_length: Optional[int] = 11  # ALMA Fixed RSI length
    alma_fixed_vwma_length: Optional[int] = 21  # ALMA Fixed VWMA length
    alma_fixed_tema_length: Optional[int] = 10  # ALMA Fixed TEMA length
    # Enterprise Cross Scanner Filters
    enable_tema_filter: Optional[bool] = False
    enable_vwap_filter: Optional[bool] = False
    enable_volume_filter_cross: Optional[bool] = False
    enable_htf_rsi_filter: Optional[bool] = False
    # CPR Narrow Filter — only show signals where CPR is Extreme Narrow or Narrow
    enable_cpr_narrow_filter: Optional[bool] = False

# ── API ROUTES ──

@app.get("/")
def serve_frontend():
    """Serve the frontend dashboard"""
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"status": "Enterprise API is running — frontend not found"}

@app.post("/api/scan")
async def trigger_scan(request: ScanRequest):
    logging.info(f"Received scan request for indices: {request.indices} and timeframes: {request.timeframes} | Speed: {request.adaptation_speed} | MinBars: {request.min_bars_between} | Scanner: {request.scanner_type}")
    try:
        # Clear log file before new scan
        open(log_file, 'w').close()
        logging.info("Starting new scan...")
        
        start_time = time.time()
        
        # Run scanner (await async call)
        results = await scanner.run_scan(
            request.indices,
            request.timeframes,
            log_file,
            adaptation_speed=request.adaptation_speed,
            min_bars_between=request.min_bars_between,
            crypto_count=request.crypto_count,
            scanner_type=request.scanner_type,
            ma_type=request.ma_type,
            auto_ma_type=request.auto_ma_type,  # Auto-select MA type based on timeframe
            enable_regime_filter=request.enable_regime_filter,  # Pass filter toggles
            enable_volume_filter=request.enable_volume_filter,
            enable_angle_filter=request.enable_angle_filter,
            hilega_buy_rsi=request.hilega_buy_rsi,
            hilega_sell_rsi=request.hilega_sell_rsi,
            hilega_rsi_mode=request.hilega_rsi_mode,
            alma_fixed_rsi_length=request.alma_fixed_rsi_length,
            alma_fixed_vwma_length=request.alma_fixed_vwma_length,
            alma_fixed_tema_length=request.alma_fixed_tema_length,
            enable_tema_filter=request.enable_tema_filter,
            enable_vwap_filter=request.enable_vwap_filter,
            enable_volume_filter_cross=request.enable_volume_filter_cross,
            enable_htf_rsi_filter=request.enable_htf_rsi_filter,
            enable_cpr_narrow_filter=request.enable_cpr_narrow_filter,
        )
        
        duration = round(time.time() - start_time, 2)
        scan_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Separate HILEGA, Cross, Conflict, Gap, and AMA/Qwen results
        hilega_results = []
        cross_results = []
        conflict_results = []
        gap_results = []
        ama_qwen_results = []

        for result in results:
            scanner_label = result.get('Scanner', '')
            if 'HILEGA' in scanner_label:
                hilega_results.append(result)
            elif 'CROSS' in scanner_label:
                cross_results.append(result)
            elif 'Conflict' in scanner_label or 'Bar+1' in scanner_label:
                conflict_results.append(result)
            elif scanner_label == 'GAP':
                gap_results.append(result)
            else:
                ama_qwen_results.append(result)

        # Store in memory
        latest_scan["results"] = ama_qwen_results
        latest_scan["hilega_results"] = hilega_results
        latest_scan["cross_results"] = cross_results
        latest_scan["conflict_results"] = conflict_results
        latest_scan["gap_results"] = gap_results
        latest_scan["scan_time"] = scan_time
        latest_scan["duration"] = duration

        logging.info(f"Scan completed successfully in {duration}s. Found {len(ama_qwen_results)} AMA/Qwen, {len(conflict_results)} Conflict, {len(hilega_results)} HILEGA, {len(cross_results)} Cross, {len(gap_results)} Gap signal(s).")
        return {
            "status": "success",
            "data": ama_qwen_results,
            "hilega_data": hilega_results,
            "cross_data": cross_results,
            "conflict_data": conflict_results,
            "gap_data": gap_results,
            "scan_time": scan_time,
            "duration": duration
        }
    except Exception as e:
        logging.error(f"Scan failed with error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/results")
async def get_results():
    """Return the latest scan results"""
    return {
        "results": latest_scan["results"],
        "hilega_results": latest_scan["hilega_results"],
        "cross_results": latest_scan["cross_results"],
        "conflict_results": latest_scan["conflict_results"],
        "gap_results": latest_scan["gap_results"],
        "scan_time": latest_scan["scan_time"],
        "duration": latest_scan["duration"]
    }

@app.get("/api/trade-setups")
async def get_trade_setups():
    """Fetch live top 5 actionable trade setups from Binance 15m data"""

    SYMBOLS = [
        'BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT',
        'DOGEUSDT','AVAXUSDT','LINKUSDT','ADAUSDT','NEARUSDT',
        'APTUSDT','DOTUSDT','LTCUSDT','ATOMUSDT','SUIUSDT',
        'INJUSDT','OPUSDT','ARBUSDT','SEIUSDT','TIAUSDT'
    ]

    def fmt_price(price):
        if price >= 1000:  return round(price, 2)
        elif price >= 10:  return round(price, 3)
        elif price >= 1:   return round(price, 4)
        else:              return round(price, 5)

    setups = []

    try:
        async with httpx.AsyncClient(timeout=20) as client:

            # 1. Fetch 24hr tickers for all symbols individually (reliable)
            tickers = {}
            for sym in SYMBOLS:
                try:
                    r = await client.get('https://api.binance.com/api/v3/ticker/24hr',
                                         params={'symbol': sym})
                    if r.status_code == 200:
                        tickers[sym] = r.json()
                except Exception:
                    pass

            # 2. Fetch 1h data for target ranges (instead of 24h extremes)
            hourly_ranges = {}
            for sym in SYMBOLS:
                try:
                    r = await client.get('https://api.binance.com/api/v3/klines',
                                         params={'symbol': sym, 'interval': '1h', 'limit': 24})
                    if r.status_code == 200:
                        raw = r.json()
                        if isinstance(raw, list) and len(raw) >= 2:
                            highs = [float(k[2]) for k in raw[:-1]]  # exclude forming candle
                            lows = [float(k[3]) for k in raw[:-1]]
                            hourly_ranges[sym] = {
                                'high_1h': max(highs) if highs else 0,
                                'low_1h': min(lows) if lows else 0
                            }
                except Exception:
                    pass

            # 2. Analyse each symbol
            for symbol in SYMBOLS:
                try:
                    if symbol not in tickers:
                        continue

                    t = tickers[symbol]
                    price_change_pct = float(t['priceChangePercent'])
                    high_24h         = float(t['highPrice'])
                    low_24h          = float(t['lowPrice'])
                    quote_vol        = float(t['quoteVolume'])

                    # Get 1h range for targets (fallback to 24h if not available)
                    high_target = hourly_ranges.get(symbol, {}).get('high_1h', high_24h)
                    low_target = hourly_ranges.get(symbol, {}).get('low_1h', low_24h)

                    # Fetch 15m klines
                    kr = await client.get('https://api.binance.com/api/v3/klines',
                                          params={'symbol': symbol, 'interval': '15m', 'limit': 60})
                    raw = kr.json()
                    if not isinstance(raw, list) or len(raw) < 20:
                        continue

                    candles = [{'open': float(k[1]), 'high': float(k[2]),
                                'low':  float(k[3]), 'close': float(k[4]),
                                'vol':  float(k[5])} for k in raw]

                    closed   = candles[:-1]          # exclude forming candle
                    current  = candles[-1]['close']

                    # ── Volume ───────────────────────────────────────────────
                    vols      = [c['vol'] for c in closed]
                    avg_vol   = statistics.mean(vols) if vols else 1
                    last_vol  = closed[-1]['vol']
                    vol_ratio = round(last_vol / avg_vol, 1) if avg_vol else 1.0

                    # ── Trend (last 6 closed candles) ─────────────────────────
                    last6     = closed[-6:]
                    bull_cnt  = sum(1 for c in last6 if c['close'] > c['open'])
                    bear_cnt  = 6 - bull_cnt
                    if bull_cnt >= 4:    trend = 'UP'
                    elif bear_cnt >= 4:  trend = 'DOWN'
                    else:                trend = 'NEUTRAL'

                    # ── Support / Resistance from last 30 candles ─────────────
                    window30    = closed[-30:]
                    recent_high = max(c['high'] for c in window30)
                    recent_low  = min(c['low']  for c in window30)
                    range_size  = recent_high - recent_low or current * 0.01

                    # Swing highs / lows (window=3 so we always find some)
                    s_highs, s_lows = [], []
                    for i in range(3, len(closed) - 3):
                        if closed[i]['high'] >= max(closed[j]['high'] for j in range(i-3, i+4)):
                            s_highs.append(closed[i]['high'])
                        if closed[i]['low']  <= min(closed[j]['low']  for j in range(i-3, i+4)):
                            s_lows.append(closed[i]['low'])

                    res_above = sorted([h for h in s_highs if h > current * 1.001])
                    sup_below = sorted([l for l in s_lows  if l < current * 0.999], reverse=True)

                    resistance = res_above[0] if res_above else recent_high
                    support    = sup_below[0] if sup_below else recent_low

                    price_pos  = (current - recent_low) / range_size   # 0=bottom, 1=top

                    # Use recent swing levels for tight SL, 24h extremes for wide TP
                    # This gives naturally better R:R across all market conditions

                    # ── Try LONG setup ───────────────────────────────────────
                    long_entry  = current
                    long_sl     = support * 0.998          # just below nearest support
                    if long_sl >= long_entry:
                        long_sl = current * 0.99          # fallback when price has moved below prior support
                    long_tp1    = current + (high_target - current) * 0.5
                    long_tp2    = high_target              # target 1h high
                    long_risk   = long_entry - long_sl
                    long_reward = long_tp2 - long_entry
                    long_rr     = (long_reward / long_risk) if long_risk > 0 else 0

                    # ── Try SHORT setup ──────────────────────────────────────
                    short_entry  = current
                    short_sl     = resistance * 1.002      # just above nearest resistance
                    if short_sl <= short_entry:
                        short_sl = current * 1.01       # fallback when price has moved above prior resistance
                    short_tp1    = current - (current - low_target) * 0.5
                    short_tp2    = low_target              # target 1h low
                    short_risk   = short_sl - short_entry
                    short_reward = short_entry - short_tp2
                    short_rr     = (short_reward / short_risk) if short_risk > 0 else 0

                    # ── Pick the setup with better R:R that aligns with trend ─
                    # Prefer trend-aligned; both must be >= 1.5 to be considered
                    MIN_RR = 1.5
                    candidate = None

                    if trend == 'UP' and long_rr >= MIN_RR:
                        candidate = 'LONG'
                    elif trend == 'DOWN' and short_rr >= MIN_RR:
                        candidate = 'SHORT'
                    elif trend == 'NEUTRAL':
                        # Pick whichever has better R:R
                        if long_rr >= MIN_RR and long_rr >= short_rr:
                            candidate = 'LONG'
                        elif short_rr >= MIN_RR:
                            candidate = 'SHORT'
                    else:
                        # Trend exists but counter-trend has better R:R — skip
                        pass

                    if candidate is None:
                        continue   # no quality setup for this coin right now

                    if candidate == 'LONG':
                        signal     = 'LONG'
                        entry      = fmt_price(long_entry)
                        sl         = fmt_price(long_sl)
                        tp1        = fmt_price(long_tp1)
                        tp2        = fmt_price(long_tp2)
                        risk       = long_risk
                        reward     = long_reward
                        rr         = round(long_rr, 1)
                        if price_pos >= 0.65 and vol_ratio >= 1.3:   setup_type = 'BREAKOUT'
                        elif price_pos <= 0.35:                        setup_type = 'RANGE BOUNCE'
                        else:                                          setup_type = 'PULLBACK'
                        reasons = [
                            f"{'↑ Uptrend' if trend=='UP' else '→ Bullish momentum'}: {bull_cnt}/6 candles bullish · 24h {'+' if price_change_pct>=0 else ''}{price_change_pct:.2f}%",
                            f"SL placed below support ${fmt_price(support)} · Target resistance ${fmt_price(resistance)}",
                            f"Price at {round(price_pos*100)}% of 30-candle range · Setup: {setup_type}",
                            f"Volume {vol_ratio}× avg · ${round(quote_vol/1e6,1)}M traded today"
                        ]
                    else:
                        signal     = 'SHORT'
                        entry      = fmt_price(short_entry)
                        sl         = fmt_price(short_sl)
                        tp1        = fmt_price(short_tp1)
                        tp2        = fmt_price(short_tp2)
                        risk       = short_risk
                        reward     = short_reward
                        rr         = round(short_rr, 1)
                        if price_pos <= 0.35 and vol_ratio >= 1.3:   setup_type = 'BREAKDOWN'
                        elif price_pos >= 0.65:                        setup_type = 'RANGE SHORT'
                        else:                                          setup_type = 'PULLBACK SHORT'
                        reasons = [
                            f"↓ Downtrend: {bear_cnt}/6 candles bearish · 24h {price_change_pct:.2f}%",
                            f"SL placed above resistance ${fmt_price(resistance)} · Target support ${fmt_price(support)}",
                            f"Price at {round(price_pos*100)}% of 30-candle range · Setup: {setup_type}",
                            f"Volume {vol_ratio}× avg · ${round(quote_vol/1e6,1)}M traded today"
                        ]

                    risk_pct   = round(risk / entry * 100, 2)
                    reward_pct = round(reward / entry * 100, 2)

                    # Composite score — higher is better
                    score = (rr * 4) + (vol_ratio * 1.5) + (abs(price_change_pct) * 0.3)
                    if trend != 'NEUTRAL': score += 3
                    if vol_ratio >= 1.5:   score += 2

                    setups.append({
                        'symbol':           symbol.replace('USDT', '/USDT'),
                        'signal':           signal,
                        'setup_type':       setup_type,
                        'current_price':    fmt_price(current),
                        'entry':            entry,
                        'stop_loss':        sl,
                        'target_1':         tp1,
                        'target_2':         tp2,
                        'risk_pct':         risk_pct,
                        'reward_pct':       reward_pct,
                        'rr':               rr,
                        'volume_ratio':     vol_ratio,
                        'price_change_24h': round(price_change_pct, 2),
                        'justification':    reasons,
                        'timeframe':        '15m',
                        '_score':           round(score, 2)
                    })

                except Exception as e:
                    logging.warning(f"[trade-setups] Skipping {symbol}: {e}")
                    continue

    except Exception as e:
        logging.error(f"[trade-setups] Fatal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Sort strictly by Reward:Risk — highest to lowest
    setups.sort(key=lambda x: x['rr'], reverse=True)
    for s in setups:
        s.pop('_score', None)

    return {
        'setups': setups[:7],
        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/api/market-heatmap")
async def get_market_heatmap():
    """Fetch live market heatmap using same technical analysis as Trade Setups, trying multiple timeframes to show all 7 cryptos"""

    SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT', 'AAVEUSDT']

    def fmt_price(price):
        if price >= 1000:  return round(price, 2)
        elif price >= 10:  return round(price, 3)
        elif price >= 1:   return round(price, 4)
        else:              return round(price, 5)

    async def analyze_symbol(client, symbol, timeframe, limit, min_candles=12):
        """Analyze a symbol with given timeframe, return setup dict or None"""
        try:
            # Fetch ticker data
            tr = await client.get('https://api.binance.com/api/v3/ticker/24hr', params={'symbol': symbol})
            if tr.status_code != 200:
                return None
            t = tr.json()

            price_change_pct = float(t['priceChangePercent'])
            high_24h = float(t['highPrice'])
            low_24h = float(t['lowPrice'])
            quote_vol = float(t.get('quoteVolume') or t.get('quoteAssetVolume') or 0)
            current = float(t['lastPrice'])

            # For 1h timeframe, get 12h/24h data for targets
            target_high = high_24h
            target_low = low_24h
            if timeframe == '1h':
                # Get 12h range for more realistic targets
                try:
                    kr12h = await client.get('https://api.binance.com/api/v3/klines',
                                             params={'symbol': symbol, 'interval': '12h', 'limit': 14})  # 7 days
                    if kr12h.status_code == 200:
                        raw12h = kr12h.json()
                        if isinstance(raw12h, list) and len(raw12h) >= 2:
                            highs12h = [float(k[2]) for k in raw12h[:-1]]
                            lows12h = [float(k[3]) for k in raw12h[:-1]]
                            target_high = max(highs12h) if highs12h else high_24h
                            target_low = min(lows12h) if lows12h else low_24h
                except:
                    pass  # fallback to 24h

            # Fetch klines for analysis timeframe
            kr = await client.get('https://api.binance.com/api/v3/klines',
                                 params={'symbol': symbol, 'interval': timeframe, 'limit': limit})
            if kr.status_code != 200:
                return None
            raw = kr.json()
            if not isinstance(raw, list) or len(raw) < min_candles:
                return None

            candles = [{'open': float(k[1]), 'high': float(k[2]),
                        'low':  float(k[3]), 'close': float(k[4]),
                        'vol':  float(k[5])} for k in raw]

            closed = candles[:-1]  # exclude forming candle

            # ── Volume Analysis ──────────────────────────────────────
            vols = [c['vol'] for c in closed]
            avg_vol = statistics.mean(vols) if vols else 1
            last_vol = closed[-1]['vol']
            vol_ratio = round(last_vol / avg_vol, 1) if avg_vol else 1.0

            # ── Trend (last 6 candles) ────────────────────────────────
            last6 = closed[-6:]
            bull_cnt = sum(1 for c in last6 if c['close'] > c['open'])
            bear_cnt = 6 - bull_cnt
            if bull_cnt >= 4:    trend = 'UP'
            elif bear_cnt >= 4:  trend = 'DOWN'
            else:                trend = 'NEUTRAL'

            # ── Support / Resistance from last 30 candles ──────────────
            window30 = closed[-30:]
            recent_high = max(c['high'] for c in window30)
            recent_low = min(c['low'] for c in window30)
            range_size = recent_high - recent_low or current * 0.01

            # Swing highs / lows
            s_highs, s_lows = [], []
            for i in range(3, len(closed) - 3):
                if closed[i]['high'] >= max(closed[j]['high'] for j in range(i-3, i+4)):
                    s_highs.append(closed[i]['high'])
                if closed[i]['low'] <= min(closed[j]['low'] for j in range(i-3, i+4)):
                    s_lows.append(closed[i]['low'])

            res_above = sorted([h for h in s_highs if h > current * 1.001])
            sup_below = sorted([l for l in s_lows if l < current * 0.999], reverse=True)

            resistance = res_above[0] if res_above else recent_high
            support = sup_below[0] if sup_below else recent_low

            price_pos = (current - recent_low) / range_size

            # ── LONG Setup ──────────────────────────────────────────
            long_entry = current
            long_sl = support * 0.998
            if long_sl >= long_entry:
                long_sl = current * 0.99
            long_tp1 = current + (target_high - current) * 0.4
            long_tp2 = target_high
            long_risk = long_entry - long_sl
            long_reward = long_tp2 - long_entry
            long_rr = (long_reward / long_risk) if long_risk > 0 else 0

            # ── SHORT Setup ─────────────────────────────────────────
            short_entry = current
            short_sl = resistance * 1.002
            if short_sl <= short_entry:
                short_sl = current * 1.01
            short_tp1 = current - (current - target_low) * 0.4
            short_tp2 = target_low
            short_risk = short_sl - short_entry
            short_reward = short_entry - short_tp2
            short_rr = (short_reward / short_risk) if short_risk > 0 else 0

            # ── Pick the best setup aligned with trend ────────────────
            MIN_RR = 1.0  # Lower threshold for heatmap to show more cryptos
            candidate = None

            if trend == 'UP' and long_rr >= MIN_RR:
                candidate = 'LONG'
            elif trend == 'DOWN' and short_rr >= MIN_RR:
                candidate = 'SHORT'
            elif trend == 'NEUTRAL':
                if long_rr >= MIN_RR and long_rr >= short_rr:
                    candidate = 'LONG'
                elif short_rr >= MIN_RR:
                    candidate = 'SHORT'

            if candidate is None:
                return None  # No valid setup found

            if candidate == 'LONG':
                signal = 'LONG'
                entry = fmt_price(long_entry)
                sl = fmt_price(long_sl)
                tp1 = fmt_price(long_tp1)
                tp2 = fmt_price(long_tp2)
                risk = long_risk
                reward = long_reward
                rr = round(long_rr, 1)
                if price_pos >= 0.65 and vol_ratio >= 1.3:
                    setup_type = 'BREAKOUT'
                elif price_pos <= 0.35:
                    setup_type = 'RANGE BOUNCE'
                else:
                    setup_type = 'PULLBACK'
                reasons = [
                    f"{'↑ Uptrend' if trend == 'UP' else '→ Bullish momentum'}: {bull_cnt}/6 candles bullish · {'+' if price_change_pct >= 0 else ''}{price_change_pct:.2f}%",
                    f"SL below support ${fmt_price(support)} · Target ${fmt_price(resistance)}",
                    f"Price at {round(price_pos*100)}% of range",
                    f"Volume {vol_ratio}× avg · ${round(quote_vol/1e6, 1)}M daily"
                ]
            else:
                signal = 'SHORT'
                entry = fmt_price(short_entry)
                sl = fmt_price(short_sl)
                tp1 = fmt_price(short_tp1)
                tp2 = fmt_price(short_tp2)
                risk = short_risk
                reward = short_reward
                rr = round(short_rr, 1)
                if price_pos <= 0.35 and vol_ratio >= 1.3:
                    setup_type = 'BREAKDOWN'
                elif price_pos >= 0.65:
                    setup_type = 'RANGE SHORT'
                else:
                    setup_type = 'PULLBACK SHORT'
                reasons = [
                    f"↓ Downtrend: {bear_cnt}/6 candles bearish · {price_change_pct:.2f}%",
                    f"SL above resistance ${fmt_price(resistance)} · Target ${fmt_price(support)}",
                    f"Price at {round(price_pos*100)}% of range",
                    f"Volume {vol_ratio}× avg · ${round(quote_vol/1e6, 1)}M daily"
                ]

            risk_pct = round((risk / entry * 100), 2) if entry else 0
            reward_pct = round((reward / entry * 100), 2) if entry else 0

            return {
                'symbol': symbol.replace('USDT', '/USDT'),
                'signal': signal,
                'setup_type': setup_type,
                'current_price': fmt_price(current),
                'entry': entry,
                'stop_loss': sl,
                'target_1': tp1,
                'target_2': tp2,
                'risk_pct': risk_pct,
                'reward_pct': reward_pct,
                'rr': rr,
                'price_change_pct': round(price_change_pct, 2),
                'price_change_usd': fmt_price(abs(float(t.get('priceChange') or 0))),
                'price_direction': 'up' if price_change_pct >= 0 else 'down',
                'justification': reasons,
                'timeframe': timeframe,
                'volume_24h': round(quote_vol / 1e6, 1),
                'price_range': f"${fmt_price(low_24h)} - ${fmt_price(high_24h)}"
            }

        except Exception as e:
            logging.warning(f"[market-heatmap] Failed to analyze {symbol} on {timeframe}: {e}")
            return None

    heatmap_data = []

    try:
        async with httpx.AsyncClient(timeout=20) as client:

            # For each symbol, try timeframes in order: 1d, 12h, 2d
            for symbol in SYMBOLS:
                setup = None

                # Try 1h (hourly) first - 168 candles for 7 days
                setup = await analyze_symbol(client, symbol, '1h', 168, 24)
                if setup:
                    heatmap_data.append(setup)
                    continue

                # Try 12h (12-hour) - 168 candles for 84 days worth
                setup = await analyze_symbol(client, symbol, '12h', 168, 12)
                if setup:
                    heatmap_data.append(setup)
                    continue

                # Try 2d (2-day) - 90 candles for 180 days worth
                setup = await analyze_symbol(client, symbol, '2d', 90, 12)
                if setup:
                    heatmap_data.append(setup)
                    continue

                # If no timeframe worked, create a basic entry with current price data
                try:
                    tr = await client.get('https://api.binance.com/api/v3/ticker/24hr', params={'symbol': symbol})
                    if tr.status_code == 200:
                        t = tr.json()
                        current = float(t['lastPrice'])
                        price_change_pct = float(t['priceChangePercent'])
                        quote_vol = float(t.get('quoteVolume') or t.get('quoteAssetVolume') or 0)

                        # Basic setup with no technical analysis
                        signal = 'LONG' if price_change_pct >= 0 else 'SHORT'
                        setup_type = 'MARKET TREND'
                        entry = fmt_price(current)
                        if signal == 'LONG':
                            sl = fmt_price(current * 0.95)  # 5% below for LONG stop loss
                            tp1 = fmt_price(current * 1.05)  # 5% above for LONG target 1
                            tp2 = fmt_price(current * 1.10)  # 10% above for LONG target 2
                        else:  # SHORT
                            sl = fmt_price(current * 1.05)  # 5% above for SHORT stop loss
                            tp1 = fmt_price(current * 0.95)  # 5% below for SHORT target 1
                            tp2 = fmt_price(current * 0.90)  # 10% below for SHORT target 2
                        risk = abs(current - float(sl))
                        reward = abs(float(tp2) - current)
                        rr = round((reward / risk) if risk > 0 else 0, 1)
                        risk_pct = 5.0
                        reward_pct = 10.0

                        reasons = [
                            f"Market trend: {'+' if price_change_pct >= 0 else ''}{price_change_pct:.2f}% 24h change",
                            f"Basic setup - no technical confirmation available",
                            f"Volume ${round(quote_vol/1e6, 1)}M daily"
                        ]

                        heatmap_data.append({
                            'symbol': symbol.replace('USDT', '/USDT'),
                            'signal': signal,
                            'setup_type': setup_type,
                            'current_price': entry,
                            'entry': entry,
                            'stop_loss': sl,
                            'target_1': tp1,
                            'target_2': tp2,
                            'risk_pct': risk_pct,
                            'reward_pct': reward_pct,
                            'rr': rr,
                            'price_change_pct': round(price_change_pct, 2),
                            'price_change_usd': fmt_price(abs(float(t.get('priceChange') or 0))),
                            'price_direction': 'up' if price_change_pct >= 0 else 'down',
                            'justification': reasons,
                            'timeframe': 'market',
                            'volume_24h': round(quote_vol / 1e6, 1),
                            'price_range': f"${fmt_price(float(t['lowPrice']))} - ${fmt_price(float(t['highPrice']))}"
                        })
                except Exception as e:
                    logging.warning(f"[market-heatmap] Could not create basic entry for {symbol}: {e}")

    except Exception as e:
        logging.error(f"[market-heatmap] Fatal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Sort by R:R descending
    heatmap_data.sort(key=lambda x: x['rr'], reverse=True)

    return {
        'heatmap': heatmap_data,
        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


@app.get("/api/logs")
def get_logs():
    try:
        if not os.path.exists(log_file):
            return {"logs": []}
        with open(log_file, 'r') as f:
            lines = f.readlines()
        return {"logs": lines}
    except Exception as e:
        return {"logs": [f"Error reading logs: {str(e)}"]}

@app.get("/api/market-data")
async def get_market_data():
    """Fetch current market data for top crypto pairs (Async)"""
    try:
        top_coins = await scanner.get_top_binance_symbols(limit=20)
        results = []
        for coin in top_coins:
            price = coin.get('price')
            price_str = f"{price:,.2f}" if price is not None else "N/A"
            change = coin.get('change', 0)
            if change is None:
                change = 0
            results.append({
                "name": coin['symbol'].replace('/USDT', '').replace(':USDT', ''),
                "price": price_str,
                "change": f"{change:+.2f}"
            })
        return {"indices": results}
    except Exception as e:
        logging.error(f"Market data error: {e}")
        return {"indices": []}

@app.get("/api/status")
def get_status():
    """Return current API status"""
    return {
        "status": "online",
        "version": "2.0 Enterprise",
        "uptime": "active"
    }

# Serve static frontend files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

@app.on_event("shutdown")
async def shutdown_event():
    logging.info("Shutting down Enterprise API...")
    await scanner.close_exchange()

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  🚀 Gemini Scanner Enterprise — Starting Server")
    print("=" * 60)
    print(f"\n  Dashboard: http://localhost:8001")
    print(f"  API Docs:  http://localhost:8001/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8001)
