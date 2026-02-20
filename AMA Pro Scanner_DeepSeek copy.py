"""
AMA Pro Scanner - High-Performance Edition
Phases 1-3 Complete Implementation

Features:
- Async/await architecture (Phase 2)
- WebSocket streaming for real-time data (Phase 2)
- Smart caching with TTL and freshness indicators (Phase 1)
- Connection pooling (Phase 1)
- Adaptive rate limiting (Phase 1)
- Real-time terminal dashboard (Phase 2)
- Distributed processing support (Phase 3)
- Redis caching layer (Phase 3)
- ML-enhanced predictions (Phase 3)
- Fixed 5-candle rule validation
"""

import asyncio
import aiohttp
import aioredis
import numpy as np
import pandas as pd
import json
import time
import datetime
import warnings
import sys
import os
import signal
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from contextlib import asynccontextmanager
import async_timeout
import websockets
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib
import argparse
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich import box
import signal
import logging
from logging.handlers import RotatingFileHandler
import hashlib
import pickle
import redis.asyncio as redis

# Suppress warnings
warnings.filterwarnings("ignore")

# =============================================================================
# Configuration & Constants
# =============================================================================

@dataclass
class ScannerConfig:
    """Central configuration for the scanner"""
    # Exchange settings
    exchange_id: str = 'binance'
    exchange_type: str = 'future'  # future, spot, margin
    
    # Scan settings
    symbol_limit: int = 500
    timeframes: List[str] = field(default_factory=lambda: ['15m', '30m', '1h', '2h', '4h', '1d'])
    
    # Performance settings
    max_concurrent_symbols: int = 50  # Phase 1: Increased from 2
    websocket_reconnect: bool = True
    cache_ttl_seconds: int = 30  # Phase 1: Smart caching
    
    # Rate limiting (adaptive - Phase 1)
    rate_limit_calls_per_minute: int = 1200
    rate_limit_window: int = 60
    
    # WebSocket settings (Phase 2)
    use_websocket: bool = True
    websocket_ping_interval: int = 20
    websocket_timeout: int = 10
    
    # Redis settings (Phase 3)
    redis_enabled: bool = True
    redis_host: str = 'localhost'
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    # ML settings (Phase 3)
    ml_enabled: bool = True
    model_cache_size: int = 100
    
    # Email settings
    gmail_user: str = 'sahooaiagent@gmail.com'
    gmail_password: str = os.environ.get('GMAIL_APP_PASSWORD', 'ssdh izdy otpd ldee')
    receiver_email: str = 'sahooaiagent@gmail.com'
    
    # File cleanup
    keep_last_results: int = 10

# Timeframe mapping for resampling
TIMEFRAME_MAPPING = {
    '1m': '1min',
    '3m': '3min',
    '5m': '5min',
    '15m': '15min',
    '30m': '30min',
    '1h': '1h',
    '2h': '2h',
    '3h': '3h',
    '4h': '4h',
    '5h': '5h',
    '6h': '6h',
    '8h': '8h',
    '12h': '12h',
    '1d': '1d',
    '3d': '3d',
    '1w': '1w',
    '1M': '1ME'
}

# WebSocket streams by exchange (Phase 2)
WEBSOCKET_STREAMS = {
    'binance': {
        'future': 'wss://fstream.binance.com/ws',
        'spot': 'wss://stream.binance.com:9443/ws'
    },
    'mexc': {
        'future': 'wss://wbs.mexc.com/ws'
    }
}

# =============================================================================
# Data Models
# =============================================================================

@dataclass
class CachedData:
    """Cache entry with freshness tracking (Phase 1)"""
    data: Any
    timestamp: float
    freshness: str  # 🟢 Fresh, 🟡 Moderate, 🔴 Stale
    ttl: int
    
    def is_fresh(self) -> bool:
        age = time.time() - self.timestamp
        return age < self.ttl
    
    def get_freshness_emoji(self) -> str:
        age = time.time() - self.timestamp
        if age < 60:
            return "🟢 Fresh"
        elif age < 300:
            return "🟡 Moderate"
        else:
            return "🔴 Stale"

@dataclass
class Signal:
    """Trading signal data structure"""
    symbol: str
    exchange: str
    timeframe: str
    signal_type: str  # LONG or SHORT
    angle: float
    price: float
    daily_change: float
    timestamp: str
    confidence: float = 0.0  # Phase 3: ML confidence score
    volume: float = 0.0
    regime: str = ''
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_csv_row(self) -> List:
        return [
            self.symbol, self.exchange, self.timeframe, self.signal_type,
            f"{self.angle:.2f}°", f"{self.daily_change:.2f}%", self.timestamp,
            f"{self.confidence:.2f}", self.regime
        ]

@dataclass
class MarketData:
    """Real-time market data from WebSocket (Phase 2)"""
    symbol: str
    exchange: str
    timestamp: float
    price: float
    volume_24h: float
    price_change_24h: float
    bid: float
    ask: float
    spread: float

# =============================================================================
# Rate Limiter (Adaptive - Phase 1)
# =============================================================================

class AdaptiveRateLimiter:
    """Smart rate limiter with adaptive delays based on API response"""
    
    def __init__(self, max_calls_per_minute: int = 1200):
        self.max_calls = max_calls_per_minute
        self.calls: Dict[str, List[float]] = defaultdict(list)
        self.response_times: List[float] = []
        self.adaptive_delay = 0.05  # Start with 50ms base delay
        self.lock = asyncio.Lock()
        
    async def acquire(self, key: str = "default"):
        """Acquire permission to make an API call"""
        async with self.lock:
            now = time.time()
            
            # Clean old calls
            self.calls[key] = [t for t in self.calls[key] if now - t < 60]
            
            # Check if we're rate limited
            if len(self.calls[key]) >= self.max_calls:
                # Calculate sleep time based on oldest call
                oldest = self.calls[key][0]
                sleep_time = 60 - (now - oldest)
                if sleep_time > 0:
                    # Adaptive: adjust based on recent response times
                    avg_response = np.mean(self.response_times[-10:]) if self.response_times else 0.1
                    sleep_time = max(sleep_time, avg_response * 2)
                    await asyncio.sleep(sleep_time)
            
            # Record this call
            self.calls[key].append(now)
    
    def record_response_time(self, response_time: float):
        """Record API response time for adaptive delay calculation"""
        self.response_times.append(response_time)
        if len(self.response_times) > 100:
            self.response_times.pop(0)
        
        # Adjust base delay based on recent performance
        if len(self.response_times) > 10:
            p95 = np.percentile(self.response_times[-10:], 95)
            self.adaptive_delay = max(0.01, min(0.5, p95 * 1.5))

# =============================================================================
# Cache Manager (Phase 1 & 3)
# =============================================================================

class CacheManager:
    """Multi-layer cache with Redis support (Phase 3)"""
    
    def __init__(self, config: ScannerConfig):
        self.config = config
        self.memory_cache: Dict[str, CachedData] = {}
        self.redis: Optional[redis.Redis] = None
        self.stats = {
            'hits': 0,
            'misses': 0,
            'redis_hits': 0,
            'redis_misses': 0
        }
        
    async def initialize(self):
        """Initialize cache (including Redis if enabled)"""
        if self.config.redis_enabled:
            try:
                self.redis = await redis.Redis(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    db=self.config.redis_db,
                    password=self.config.redis_password,
                    decode_responses=False
                )
                await self.redis.ping()
                print(f"✅ Redis connected at {self.config.redis_host}:{self.config.redis_port}")
            except Exception as e:
                print(f"⚠️ Redis connection failed: {e}. Using memory cache only.")
                self.redis = None
    
    async def get(self, key: str) -> Optional[Any]:
        """Get from cache with freshness tracking"""
        # Check memory cache first (fastest)
        if key in self.memory_cache:
            cached = self.memory_cache[key]
            if cached.is_fresh():
                self.stats['hits'] += 1
                return cached.data
            else:
                # Stale, remove from memory
                del self.memory_cache[key]
        
        # Check Redis if available (Phase 3)
        if self.redis:
            try:
                redis_data = await self.redis.get(f"cache:{key}")
                if redis_data:
                    cached = pickle.loads(redis_data)
                    if time.time() - cached.timestamp < cached.ttl:
                        # Promote to memory cache
                        self.memory_cache[key] = cached
                        self.stats['redis_hits'] += 1
                        return cached.data
            except Exception:
                pass
        
        self.stats['misses'] += 1
        return None
    
    async def set(self, key: str, data: Any, ttl: int = 30):
        """Set cache entry with TTL"""
        cached = CachedData(
            data=data,
            timestamp=time.time(),
            freshness="🟢 Fresh",
            ttl=ttl
        )
        
        # Memory cache
        self.memory_cache[key] = cached
        
        # Redis cache (Phase 3)
        if self.redis:
            try:
                await self.redis.setex(
                    f"cache:{key}",
                    ttl,
                    pickle.dumps(cached)
                )
            except Exception as e:
                pass  # Redis failure, continue with memory cache
    
    async def cleanup(self):
        """Clean up stale cache entries"""
        current_time = time.time()
        stale_keys = [
            key for key, cached in self.memory_cache.items()
            if current_time - cached.timestamp > cached.ttl
        ]
        for key in stale_keys:
            del self.memory_cache[key]
    
    def get_stats(self) -> Dict:
        """Get cache performance statistics"""
        total = self.stats['hits'] + self.stats['misses']
        redis_total = self.stats['redis_hits'] + self.stats['redis_misses']
        
        return {
            'memory_hit_rate': f"{(self.stats['hits'] / total * 100):.1f}%" if total > 0 else "0%",
            'redis_hit_rate': f"{(self.stats['redis_hits'] / redis_total * 100):.1f}%" if redis_total > 0 else "0%",
            'memory_entries': len(self.memory_cache)
        }

# =============================================================================
# WebSocket Manager (Phase 2)
# =============================================================================

class WebSocketManager:
    """Manages WebSocket connections for real-time data"""
    
    def __init__(self, config: ScannerConfig, cache: CacheManager):
        self.config = config
        self.cache = cache
        self.connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)  # stream -> symbols
        self.market_data: Dict[str, MarketData] = {}
        self.callbacks = []
        self.running = False
        self.reconnect_tasks = []
        self.lock = asyncio.Lock()
        
    async def start(self):
        """Start WebSocket connections"""
        self.running = True
        exchange = self.config.exchange_id
        url = WEBSOCKET_STREAMS.get(exchange, {}).get(self.config.exchange_type)
        
        if not url:
            print(f"⚠️ No WebSocket URL for {exchange} {self.config.exchange_type}")
            return
        
        # Start main connection
        asyncio.create_task(self._run_websocket(url))
        
    async def _run_websocket(self, url: str):
        """Main WebSocket loop with auto-reconnect"""
        while self.running:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=self.config.websocket_ping_interval,
                    timeout=self.config.websocket_timeout
                ) as ws:
                    print(f"✅ WebSocket connected to {url}")
                    
                    # Subscribe to streams
                    await self._subscribe_all(ws)
                    
                    # Listen for messages
                    async for message in ws:
                        await self._handle_message(message)
                        
            except websockets.exceptions.ConnectionClosed:
                print("⚠️ WebSocket connection closed. Reconnecting...")
                if self.config.websocket_reconnect:
                    await asyncio.sleep(5)  # Wait before reconnect
            except Exception as e:
                print(f"⚠️ WebSocket error: {e}")
                if self.config.websocket_reconnect:
                    await asyncio.sleep(10)
    
    async def _subscribe_all(self, ws: websockets.WebSocketClientProtocol):
        """Subscribe to all required streams"""
        # Binance format: subscribe to ticker streams for all symbols
        if self.config.exchange_id == 'binance':
            # We'll subscribe in batches to avoid huge subscription messages
            symbols = list(self.subscriptions.keys())
            for i in range(0, len(symbols), 100):  # Binance limit: 200 streams per connection
                batch = symbols[i:i+100]
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": [f"{s.lower()}@ticker" for s in batch],
                    "id": int(time.time())
                }
                await ws.send(json.dumps(subscribe_msg))
    
    async def _handle_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            
            # Binance ticker format
            if 'e' in data and data['e'] == '24hrTicker':
                symbol = data['s']
                
                market_data = MarketData(
                    symbol=symbol,
                    exchange=self.config.exchange_id,
                    timestamp=data['E'] / 1000,
                    price=float(data['c']),
                    volume_24h=float(data['v']),
                    price_change_24h=float(data['P']),
                    bid=float(data['b']),
                    ask=float(data['a']),
                    spread=float(data['a']) - float(data['b'])
                )
                
                # Update cache
                await self.cache.set(f"price:{symbol}", market_data, ttl=5)
                
                # Trigger callbacks
                for callback in self.callbacks:
                    await callback(market_data)
                    
        except Exception as e:
            print(f"⚠️ Error handling WebSocket message: {e}")
    
    async def subscribe(self, symbol: str):
        """Subscribe to symbol updates"""
        async with self.lock:
            self.subscriptions[symbol].add('ticker')
    
    def register_callback(self, callback):
        """Register callback for market data updates"""
        self.callbacks.append(callback)
    
    async def stop(self):
        """Stop WebSocket connections"""
        self.running = False
        for task in self.reconnect_tasks:
            task.cancel()

# =============================================================================
# ML Predictor (Phase 3)
# =============================================================================

class MLPredictor:
    """Machine learning predictions for signal enhancement"""
    
    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.models = {}
        self.feature_cache = {}
        
    async def predict_signal(self, symbol: str, df: pd.DataFrame) -> Tuple[float, str]:
        """
        Predict signal confidence using ML
        Returns: (confidence_score, regime_description)
        """
        try:
            # Extract features
            features = await self._extract_features(df)
            
            # Check cache
            cache_key = f"ml_pred:{symbol}:{hashlib.md5(pickle.dumps(features)).hexdigest()}"
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
            
            # Simple ML model (in production, use XGBoost, LightGBM, etc.)
            confidence = self._calculate_confidence(features)
            
            # Determine regime
            regime = self._determine_regime(features, confidence)
            
            result = (confidence, regime)
            await self.cache.set(cache_key, result, ttl=60)  # Cache ML results for 1 minute
            
            return result
            
        except Exception as e:
            print(f"⚠️ ML prediction failed for {symbol}: {e}")
            return (0.5, 'neutral')  # Default neutral prediction
    
    async def _extract_features(self, df: pd.DataFrame) -> Dict:
        """Extract features for ML model"""
        features = {
            'rsi': df['rsi'].iloc[-1] if 'rsi' in df else 50,
            'adx': df['ADX'].iloc[-1] if 'ADX' in df else 25,
            'volume_ratio': df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1],
            'volatility': df['returns'].std() * np.sqrt(252) if 'returns' in df else 0,
            'trend_strength': abs(df['ema20'].iloc[-1] - df['ema50'].iloc[-1]) / df['close'].iloc[-1],
            'bb_position': self._calculate_bb_position(df),
            'macd_histogram': self._calculate_macd_histogram(df),
            'price_momentum': df['close'].pct_change(5).iloc[-1],
            'volume_momentum': df['volume'].pct_change(5).iloc[-1]
        }
        return features
    
    def _calculate_confidence(self, features: Dict) -> float:
        """Calculate confidence score (0-1) based on features"""
        score = 0.5  # Base score
        
        # RSI: extreme values suggest reversals
        if features['rsi'] < 30:
            score += 0.15  # Oversold
        elif features['rsi'] > 70:
            score += 0.15  # Overbought
        
        # ADX: trend strength
        if features['adx'] > 25:
            score += 0.1
        
        # Volume confirmation
        if features['volume_ratio'] > 1.5:
            score += 0.1
        elif features['volume_ratio'] < 0.5:
            score -= 0.1
        
        # Trend alignment
        if features['trend_strength'] > 0.01:
            score += 0.1
        
        return min(1.0, max(0.0, score))
    
    def _determine_regime(self, features: Dict, confidence: float) -> str:
        """Determine market regime"""
        if features['adx'] > 30:
            if features['trend_strength'] > 0.02:
                return 'strong_trend'
            return 'weak_trend'
        elif features['volatility'] > 0.5:
            return 'volatile'
        else:
            return 'ranging'
    
    def _calculate_bb_position(self, df: pd.DataFrame) -> float:
        """Calculate position within Bollinger Bands"""
        if 'bb_upper' in df and 'bb_lower' in df:
            bb_range = df['bb_upper'].iloc[-1] - df['bb_lower'].iloc[-1]
            if bb_range > 0:
                return (df['close'].iloc[-1] - df['bb_lower'].iloc[-1]) / bb_range
        return 0.5
    
    def _calculate_macd_histogram(self, df: pd.DataFrame) -> float:
        """Calculate MACD histogram"""
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        return (macd - signal).iloc[-1]

# =============================================================================
# Technical Analysis Engine
# =============================================================================

class TechnicalAnalysisEngine:
    """High-performance technical analysis with vectorized operations"""
    
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators at once (vectorized)"""
        df = df.copy()
        
        # Returns and volatility
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        
        # EMAs (using ewm for performance)
        for period in [8, 10, 12, 14, 16, 18, 20, 21, 26, 30, 34, 38, 42, 47, 50, 55, 200]:
            df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        
        # RSI
        df['rsi'] = TechnicalAnalysisEngine.calculate_rsi(df['close'], 14)
        
        # ADX
        df['ADX'] = TechnicalAnalysisEngine.calculate_adx(df, 14)
        
        # ATR
        df['ATR'] = TechnicalAnalysisEngine.calculate_atr(df, 14)
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * bb_std
        df['bb_lower'] = df['bb_middle'] - 2 * bb_std
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        # Volatility
        df['volatility'] = df['returns'].rolling(20).std() * np.sqrt(365 * 24 * 60)  # Annualized
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        return df
    
    @staticmethod
    def calculate_rsi(series: pd.Series, length: int = 14) -> pd.Series:
        """Vectorized RSI calculation"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        
        avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
        """Vectorized ATR calculation"""
        high, low, close = df['high'], df['low'], df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.ewm(alpha=1/length, adjust=False).mean()
        return atr
    
    @staticmethod
    def calculate_adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
        """Vectorized ADX calculation"""
        high, low, close = df['high'], df['low'], df['close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/length, adjust=False).mean()
        
        # Directional Movement
        up = high - high.shift()
        down = low.shift() - low
        
        plus_dm = np.where((up > down) & (up > 0), up, 0)
        minus_dm = np.where((down > up) & (down > 0), down, 0)
        
        plus_di = 100 * (pd.Series(plus_dm, index=high.index).ewm(alpha=1/length, adjust=False).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm, index=high.index).ewm(alpha=1/length, adjust=False).mean() / atr)
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(alpha=1/length, adjust=False).mean()
        
        return adx

# =============================================================================
# Signal Detector (AMA Pro Logic) - FIXED VERSION
# =============================================================================

class AMAProSignalDetector:
    """Core signal detection logic (optimized) with fixed 5-candle rule"""
    
    def __init__(self, ml_predictor: Optional[MLPredictor] = None):
        self.ml_predictor = ml_predictor
        
    async def detect_signals(self, symbol: str, df: pd.DataFrame, timeframe: str) -> List[Signal]:
        """Detect signals in the dataframe"""
        signals = []
        
        if df is None or len(df) < 100:
            return signals
        
        # Calculate all indicators
        df = TechnicalAnalysisEngine.calculate_indicators(df)
        
        # Apply AMA Pro logic with fixed 5-candle rule
        signal_result = self._apply_ama_pro_logic(df)
        
        if signal_result:
            signal_type, angle = signal_result
            
            # Get ML confidence if available (Phase 3)
            confidence = 0.5
            regime = 'unknown'
            if self.ml_predictor:
                confidence, regime = await self.ml_predictor.predict_signal(symbol, df)
            
            # Calculate daily change
            daily_change = ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
            
            signal = Signal(
                symbol=symbol,
                exchange='BINANCE',  # Will be overridden
                timeframe=timeframe,
                signal_type=signal_type,
                angle=angle,
                price=df['close'].iloc[-1],
                daily_change=daily_change,
                timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                confidence=confidence,
                volume=df['volume'].iloc[-1],
                regime=regime
            )
            signals.append(signal)
        
        return signals
    
    def _apply_ama_pro_logic(self, df: pd.DataFrame) -> Optional[Tuple[str, float]]:
        """
        Adaptive EMA Pro signal logic (fixed 5-candle rule):
        - Uses adaptive EMA periods that adjust based on market regime.
        - BUY: Adaptive fast EMA crosses ABOVE adaptive slow EMA within the last 5
          COMPLETED candles, AND the high of that BUY candle is NOT breached.
        - SELL: Adaptive fast EMA crosses BELOW adaptive slow EMA within the last 5
          COMPLETED candles, AND the low of that SELL candle is NOT breached.
        - Filters: EMA separation (0.15%), price confirmation (0.2%), regime filter.
        """
        # --- Regime Detection ---
        i_adxThreshold = 25
        i_volLookback = 50

        # Volatility regime
        df['hist_vol'] = df['log_returns'].rolling(window=i_volLookback).std() * np.sqrt(252) * 100
        df['hist_vol_mean'] = df['hist_vol'].rolling(window=i_volLookback).mean()
        df['vol_ratio'] = df['hist_vol'] / df['hist_vol_mean']

        df['volRegime'] = np.select(
            [df['vol_ratio'] > 1.3, df['vol_ratio'] < 0.7],
            ['High', 'Low'],
            default='Normal'
        )

        # Trend regime (ADX already calculated)
        df['trendRegime'] = np.where(df['ADX'] > i_adxThreshold, 'Trending', 'Ranging')

        # Direction regime (EMAs 20, 50, 200 already calculated)
        trend_up = (df['close'] > df['ema_20']) & (df['ema_20'] > df['ema_50']) & (df['ema_50'] > df['ema_200'])
        trend_down = (df['close'] < df['ema_20']) & (df['ema_20'] < df['ema_50']) & (df['ema_50'] < df['ema_200'])
        df['directionRegime'] = np.select([trend_up, trend_down], ['Bullish', 'Bearish'], default='Neutral')

        # --- Adaptive EMA Calculation ---
        i_emaFastMin, i_emaFastMax = 8, 21
        i_emaSlowMin, i_emaSlowMax = 21, 55

        vol_adjust = np.select(
            [df['volRegime'] == 'High', df['volRegime'] == 'Low'],
            [0.7, 1.3], default=1.0
        )
        trend_adjust = np.where(df['trendRegime'] == 'Trending', 0.8, 1.2)

        tf_multiplier = 1.2
        sensitivity_mult = 1.0

        combined_adjust = vol_adjust * trend_adjust * tf_multiplier * sensitivity_mult
        adjust_factor = np.clip(1.0 / combined_adjust, 0.5, 1.5)

        fast_range = i_emaFastMax - i_emaFastMin  # 13
        slow_range = i_emaSlowMax - i_emaSlowMin  # 34

        adaptive_fast_len = i_emaFastMin + fast_range * (1 - adjust_factor)
        adaptive_slow_len = i_emaSlowMin + slow_range * (1 - adjust_factor)
        adaptive_slow_len = np.maximum(adaptive_slow_len, adaptive_fast_len + 5)

        # Select nearest pre-calculated EMA for fast
        df['adaptiveEmaFast'] = np.select(
            [
                adaptive_fast_len <= 9,
                adaptive_fast_len <= 11,
                adaptive_fast_len <= 13,
                adaptive_fast_len <= 15,
                adaptive_fast_len <= 17,
                adaptive_fast_len <= 19,
            ],
            [df['ema_8'], df['ema_10'], df['ema_12'], df['ema_14'], df['ema_16'], df['ema_18']],
            default=df['ema_21']
        )

        # Select nearest pre-calculated EMA for slow
        df['adaptiveEmaSlow'] = np.select(
            [
                adaptive_slow_len <= 28,
                adaptive_slow_len <= 32,
                adaptive_slow_len <= 36,
                adaptive_slow_len <= 40,
                adaptive_slow_len <= 44,
                adaptive_slow_len <= 51,
            ],
            [df['ema_26'], df['ema_30'], df['ema_34'], df['ema_38'], df['ema_42'], df['ema_47']],
            default=df['ema_55']
        )

        # --- Crossover Detection on Adaptive EMAs ---
        df['prev_fast'] = df['adaptiveEmaFast'].shift(1)
        df['prev_slow'] = df['adaptiveEmaSlow'].shift(1)

        df['longCondition'] = (df['adaptiveEmaFast'] > df['adaptiveEmaSlow']) & (df['prev_fast'] <= df['prev_slow'])
        df['shortCondition'] = (df['adaptiveEmaFast'] < df['adaptiveEmaSlow']) & (df['prev_fast'] >= df['prev_slow'])

        # --- Signal Filters ---
        min_ema_separation_pct = 0.15
        ema_separation_pct = abs(df['adaptiveEmaFast'] - df['adaptiveEmaSlow']) / df['close'] * 100
        df['ema_separation_valid'] = ema_separation_pct >= min_ema_separation_pct

        df['price_confirms_long'] = df['close'] >= df['adaptiveEmaFast'] * 0.998
        df['price_confirms_short'] = df['close'] <= df['adaptiveEmaFast'] * 1.002

        # --- FIXED: 5-Candle Lookback with Breach Validation ---
        # Check the last 5 COMPLETED candles (indices -2 to -6)
        # We start from -2 because -1 is the current (incomplete) candle
        for i in range(2, 7):  # Check candles at positions -2, -3, -4, -5, -6
            if i > len(df) - 1:  # Not enough candles
                continue
                
            candle_idx = -i
            signal_candle = df.iloc[candle_idx]
            
            # Check for LONG signal
            if signal_candle['longCondition']:
                # Apply filters
                is_choppy = (signal_candle['trendRegime'] == 'Ranging') and (signal_candle['directionRegime'] == 'Neutral')
                
                if (signal_candle['directionRegime'] == 'Bearish' or
                    not signal_candle['ema_separation_valid'] or
                    not signal_candle['price_confirms_long'] or
                    is_choppy):
                    continue
                
                # --- FIXED: Breach validation ---
                # Get the signal candle's high
                signal_candle_high = signal_candle['high']
                
                # Check all candles AFTER the signal candle (more recent candles)
                # This includes candles from signal_idx+1 to the most recent candle
                candles_after_signal = df.iloc[candle_idx + 1:]
                
                # Check if ANY candle after the signal breached the high
                breach_detected = False
                for _, later_candle in candles_after_signal.iterrows():
                    if later_candle['high'] > signal_candle_high:
                        breach_detected = True
                        break
                
                if breach_detected:
                    continue  # Skip if high was breached
                    
                # Valid LONG signal found
                angle = self._calculate_crossover_angle(df, candle_idx)
                return ("LONG", angle)
            
            # Check for SHORT signal
            if signal_candle['shortCondition']:
                # Apply filters
                is_choppy = (signal_candle['trendRegime'] == 'Ranging') and (signal_candle['directionRegime'] == 'Neutral')
                
                if (signal_candle['directionRegime'] == 'Bullish' or
                    not signal_candle['ema_separation_valid'] or
                    not signal_candle['price_confirms_short'] or
                    is_choppy):
                    continue
                
                # --- FIXED: Breach validation ---
                # Get the signal candle's low
                signal_candle_low = signal_candle['low']
                
                # Check all candles AFTER the signal candle (more recent candles)
                candles_after_signal = df.iloc[candle_idx + 1:]
                
                # Check if ANY candle after the signal breached the low
                breach_detected = False
                for _, later_candle in candles_after_signal.iterrows():
                    if later_candle['low'] < signal_candle_low:
                        breach_detected = True
                        break
                
                if breach_detected:
                    continue  # Skip if low was breached
                    
                # Valid SHORT signal found
                angle = self._calculate_crossover_angle(df, candle_idx)
                return ("SHORT", angle)
        
        return None

    def _calculate_crossover_angle(self, df: pd.DataFrame, idx: int) -> float:
        """Calculate crossover angle using adaptive EMAs"""
        angle_lookback = min(3, abs(idx) - 1)
        if angle_lookback > 0:
            fast_slope = (df['adaptiveEmaFast'].iloc[idx] - df['adaptiveEmaFast'].iloc[idx - angle_lookback]) / angle_lookback
            slow_slope = (df['adaptiveEmaSlow'].iloc[idx] - df['adaptiveEmaSlow'].iloc[idx - angle_lookback]) / angle_lookback
            slope_diff = (fast_slope - slow_slope) / df['close'].iloc[idx]
            return float(np.degrees(np.arctan(slope_diff * 100)))
        return 0.0

# =============================================================================
# Data Fetcher (Async with Caching)
# =============================================================================

class DataFetcher:
    """Async data fetcher with caching and rate limiting"""
    
    def __init__(self, config: ScannerConfig, cache: CacheManager, rate_limiter: AdaptiveRateLimiter):
        self.config = config
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_urls = {
            'binance': 'https://fapi.binance.com',
            'mexc': 'https://api.mexc.com'
        }
        
    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession(
            headers={'User-Agent': 'Mozilla/5.0'},
            connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
        )
    
    async def get_top_symbols(self, limit: int = 100) -> List[str]:
        """Get top symbols by volume"""
        cache_key = f"top_symbols:{self.config.exchange_id}:{limit}"
        
        # Check cache
        cached = await self.cache.get(cache_key)
        if cached:
            print(f"📦 Using cached symbols (freshness: 🟢)")
            return cached
        
        await self.rate_limiter.acquire("symbols")
        
        try:
            if self.config.exchange_id == 'binance':
                url = f"{self.base_urls['binance']}/fapi/v1/ticker/24hr"
            else:
                url = f"{self.base_urls['mexc']}/api/v3/ticker/24hr"
            
            async with self.session.get(url) as response:
                data = await response.json()
                
                # Filter USDT pairs and sort by volume
                usdt_pairs = [item for item in data if 'USDT' in item['symbol']]
                sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
                
                symbols = [item['symbol'] for item in sorted_pairs[:limit]]
                
                # Cache for 5 minutes (symbols don't change often)
                await self.cache.set(cache_key, symbols, ttl=300)
                
                return symbols
                
        except Exception as e:
            print(f"❌ Error fetching symbols: {e}")
            return []
    
    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data with caching"""
        cache_key = f"ohlcv:{symbol}:{timeframe}:{limit}"
        
        # Check cache
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        await self.rate_limiter.acquire(f"ohlcv:{symbol}")
        
        start_time = time.time()
        
        try:
            if self.config.exchange_id == 'binance':
                url = f"{self.base_urls['binance']}/fapi/v1/klines"
                params = {
                    'symbol': symbol,
                    'interval': timeframe,
                    'limit': limit
                }
            else:
                url = f"{self.base_urls['mexc']}/api/v3/klines"
                params = {
                    'symbol': symbol,
                    'interval': timeframe,
                    'limit': limit
                }
            
            async with self.session.get(url, params=params) as response:
                data = await response.json()
                
                # Convert to DataFrame
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])
                
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                df = df.astype(float)
                df = df[['open', 'high', 'low', 'close', 'volume']]
                
                # Record response time for adaptive rate limiting
                response_time = time.time() - start_time
                self.rate_limiter.record_response_time(response_time)
                
                # Cache for configured TTL
                await self.cache.set(cache_key, df, ttl=self.config.cache_ttl_seconds)
                
                return df
                
        except Exception as e:
            print(f"❌ Error fetching {symbol} {timeframe}: {e}")
            return None
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()

# =============================================================================
# Real-time Dashboard (Rich Console)
# =============================================================================

class RealTimeDashboard:
    """Rich terminal dashboard for real-time monitoring (Phase 2)"""
    
    def __init__(self):
        self.console = Console()
        self.signals: List[Signal] = []
        self.stats = {
            'symbols_scanned': 0,
            'signals_found': 0,
            'scan_time': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'start_time': time.time()
        }
        self.lock = asyncio.Lock()
        self.live = None
        
    def create_layout(self) -> Layout:
        """Create dashboard layout"""
        layout = Layout()
        
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        layout["main"].split_row(
            Layout(name="stats", ratio=1),
            Layout(name="signals", ratio=2)
        )
        
        return layout
    
    def render_header(self) -> Panel:
        """Render header panel"""
        uptime = time.time() - self.stats['start_time']
        header_text = Text()
        header_text.append("🚀 AMA Pro Scanner ", style="bold cyan")
        header_text.append(f"| Uptime: {int(uptime//60)}m {int(uptime%60)}s ", style="yellow")
        header_text.append(f"| Signals: {self.stats['signals_found']} ", style="green")
        header_text.append(f"| Cache Hit Rate: {self.get_cache_hit_rate()} ", style="magenta")
        
        return Panel(header_text, style="bold white")
    
    def render_stats(self) -> Panel:
        """Render statistics panel"""
        table = Table(show_header=False, box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Symbols Scanned", f"{self.stats['symbols_scanned']}")
        table.add_row("Signals Found", f"{self.stats['signals_found']}")
        table.add_row("Scan Time", f"{self.stats['scan_time']:.2f}s")
        table.add_row("Cache Hits", f"{self.stats['cache_hits']}")
        table.add_row("Cache Misses", f"{self.stats['cache_misses']}")
        table.add_row("Cache Hit Rate", self.get_cache_hit_rate())
        
        return Panel(table, title="📊 Statistics", border_style="blue")
    
    def render_signals(self) -> Panel:
        """Render signals table"""
        table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
        table.add_column("Symbol", style="cyan")
        table.add_column("TF", style="yellow")
        table.add_column("Signal", style="bold")
        table.add_column("Angle", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Regime", style="blue")
        table.add_column("Daily Change", justify="right")
        
        for signal in self.signals[-10:]:  # Show last 10 signals
            signal_style = "green" if signal.signal_type == "LONG" else "red"
            confidence_style = "green" if signal.confidence > 0.7 else "yellow" if signal.confidence > 0.5 else "red"
            
            table.add_row(
                signal.symbol,
                signal.timeframe,
                f"[{signal_style}]{signal.signal_type}[/{signal_style}]",
                f"{signal.angle:.1f}°",
                f"[{confidence_style}]{signal.confidence:.1%}[/{confidence_style}]",
                signal.regime[:10],
                f"{signal.daily_change:+.2f}%"
            )
        
        return Panel(table, title="📈 Latest Signals", border_style="green")
    
    def render_footer(self) -> Panel:
        """Render footer panel"""
        footer_text = Text()
        footer_text.append("Press Ctrl+C to stop ", style="white")
        footer_text.append("| Cache: 🟢 Fresh", style="green")
        
        return Panel(footer_text, style="dim white")
    
    def get_cache_hit_rate(self) -> str:
        """Calculate cache hit rate"""
        total = self.stats['cache_hits'] + self.stats['cache_misses']
        if total == 0:
            return "0%"
        rate = (self.stats['cache_hits'] / total) * 100
        return f"{rate:.1f}%"
    
    async def update(self, signals: List[Signal], stats: Dict):
        """Update dashboard with new data"""
        async with self.lock:
            self.signals.extend(signals)
            for key, value in stats.items():
                if key in self.stats:
                    self.stats[key] = value
    
    async def run(self):
        """Run the dashboard"""
        with Live(self.create_layout(), refresh_per_second=4, screen=True) as live:
            self.live = live
            while True:
                layout = self.create_layout()
                layout["header"].update(self.render_header())
                layout["stats"].update(self.render_stats())
                layout["signals"].update(self.render_signals())
                layout["footer"].update(self.render_footer())
                
                live.update(layout)
                await asyncio.sleep(0.25)
    
    def stop(self):
        """Stop the dashboard"""
        if self.live:
            self.live.stop()

# =============================================================================
# Distributed Task Queue (Phase 3)
# =============================================================================

class DistributedTaskQueue:
    """Redis-based distributed task queue for multi-machine scanning"""
    
    def __init__(self, redis_client: Optional[redis.Redis]):
        self.redis = redis_client
        self.task_queue = "scanner:tasks"
        self.result_queue = "scanner:results"
        
    async def push_tasks(self, symbols: List[str], timeframes: List[str]):
        """Push scanning tasks to queue"""
        if not self.redis:
            return
            
        for symbol in symbols:
            for tf in timeframes:
                task = {
                    'symbol': symbol,
                    'timeframe': tf,
                    'timestamp': time.time()
                }
                await self.redis.rpush(self.task_queue, json.dumps(task))
    
    async def get_task(self) -> Optional[Dict]:
        """Get next task from queue"""
        if not self.redis:
            return None
            
        task_data = await self.redis.lpop(self.task_queue)
        if task_data:
            return json.loads(task_data)
        return None
    
    async def publish_result(self, signal: Signal):
        """Publish scan result"""
        if not self.redis:
            return
            
        await self.redis.rpush(self.result_queue, json.dumps(signal.to_dict()))

# =============================================================================
# Main Scanner Engine
# =============================================================================

class AMAProScanner:
    """Main scanner engine integrating all components"""
    
    def __init__(self, config: ScannerConfig):
        self.config = config
        self.cache = CacheManager(config)
        self.rate_limiter = AdaptiveRateLimiter(config.rate_limit_calls_per_minute)
        self.data_fetcher = DataFetcher(config, self.cache, self.rate_limiter)
        self.ml_predictor = MLPredictor(self.cache) if config.ml_enabled else None
        self.detector = AMAProSignalDetector(self.ml_predictor)
        self.dashboard = RealTimeDashboard()
        self.websocket_manager = WebSocketManager(config, self.cache) if config.use_websocket else None
        self.task_queue = None
        self.signals: List[Signal] = []
        self.running = False
        self.scan_stats = defaultdict(int)
        
    async def initialize(self):
        """Initialize all components"""
        print("🚀 Initializing AMA Pro Scanner (High-Performance Edition)...")
        
        # Initialize cache
        await self.cache.initialize()
        
        # Initialize data fetcher
        await self.data_fetcher.initialize()
        
        # Initialize Redis task queue if enabled
        if self.config.redis_enabled and self.cache.redis:
            self.task_queue = DistributedTaskQueue(self.cache.redis)
        
        # Initialize WebSocket manager
        if self.websocket_manager:
            await self.websocket_manager.start()
            # Register callback for real-time updates
            self.websocket_manager.register_callback(self.on_market_data)
        
        print("✅ Scanner initialized successfully")
        print(f"📊 Configuration:")
        print(f"  • Exchange: {self.config.exchange_id}")
        print(f"  • Symbols: up to {self.config.symbol_limit}")
        print(f"  • Timeframes: {', '.join(self.config.timeframes)}")
        print(f"  • Concurrent symbols: {self.config.max_concurrent_symbols}")
        print(f"  • Cache TTL: {self.config.cache_ttl_seconds}s")
        print(f"  • ML Enabled: {self.config.ml_enabled}")
        print(f"  • WebSocket: {self.config.use_websocket}")
        print()
    
    async def on_market_data(self, market_data: MarketData):
        """Handle real-time market data from WebSocket"""
        # Update cache with real-time price
        await self.cache.set(f"price:{market_data.symbol}", market_data, ttl=5)
    
    async def scan_symbol(self, symbol: str, timeframe: str) -> List[Signal]:
        """Scan a single symbol for a specific timeframe"""
        # Fetch data (with caching)
        df = await self.data_fetcher.fetch_ohlcv(symbol, timeframe)
        
        if df is None or df.empty:
            return []
        
        # Detect signals
        signals = await self.detector.detect_signals(symbol, df, timeframe)
        
        # Update exchange in signals
        for signal in signals:
            signal.exchange = self.config.exchange_id.upper()
        
        return signals
    
    async def scan_batch(self, symbols: List[str], timeframe: str) -> List[Signal]:
        """Scan a batch of symbols for a specific timeframe"""
        batch_signals = []
        
        # Use asyncio.gather for concurrent symbol scanning
        tasks = [self.scan_symbol(symbol, timeframe) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                continue
            if result:
                batch_signals.extend(result)
        
        return batch_signals
    
    async def run_scan(self):
        """Main scan execution"""
        self.running = True
        start_time = time.time()
        
        print("🔍 Fetching top symbols...")
        symbols = await self.data_fetcher.get_top_symbols(self.config.symbol_limit)
        
        if not symbols:
            print("❌ No symbols found")
            return
        
        print(f"📊 Found {len(symbols)} symbols")
        
        # Split symbols into batches for concurrent processing
        batch_size = self.config.max_concurrent_symbols
        symbol_batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
        
        all_signals = []
        
        # Scan each timeframe
        for timeframe in self.config.timeframes:
            print(f"\n⏰ Scanning timeframe: {timeframe}")
            
            timeframe_signals = []
            
            # Process batches concurrently
            batch_tasks = [self.scan_batch(batch, timeframe) for batch in symbol_batches]
            batch_results = await asyncio.gather(*batch_tasks)
            
            for signals in batch_results:
                timeframe_signals.extend(signals)
            
            all_signals.extend(timeframe_signals)
            
            # Update dashboard stats
            await self.dashboard.update(timeframe_signals, {
                'symbols_scanned': len(symbols),
                'signals_found': len(all_signals),
                'scan_time': time.time() - start_time,
                'cache_hits': self.cache.stats['hits'] + self.cache.stats['redis_hits'],
                'cache_misses': self.cache.stats['misses'] + self.cache.stats['redis_misses']
            })
            
            print(f"  • Found {len(timeframe_signals)} signals")
        
        self.signals = all_signals
        
        scan_duration = time.time() - start_time
        print(f"\n✅ Scan completed in {scan_duration:.2f} seconds")
        print(f"📊 Total signals found: {len(all_signals)}")
        
        return all_signals
    
    async def save_results(self):
        """Save results to CSV and send email"""
        if not self.signals:
            print("📧 No signals to save")
            return
        
        # Create DataFrame
        df = pd.DataFrame([s.to_dict() for s in self.signals])
        
        # Save to CSV
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"ama_pro_scan_results_{timestamp}.csv"
        df.to_csv(filename, index=False)
        print(f"💾 Results saved to {filename}")
        
        # Send email notification
        if self.config.gmail_password:
            await self.send_email_notification()
    
    async def send_email_notification(self):
        """Send email with results"""
        try:
            message = MIMEMultipart()
            message["From"] = self.config.gmail_user
            message["To"] = self.config.receiver_email
            
            if self.signals:
                message["Subject"] = f"AMA Pro Scanner: {len(self.signals)} Signals Found"
                
                body = f"AMA Pro Scanner detected {len(self.signals)} signals:\n\n"
                for signal in self.signals[-20:]:  # Last 20 signals
                    body += f"• {signal.symbol} [{signal.timeframe}] {signal.signal_type} "
                    body += f"Angle: {signal.angle:.1f}° Confidence: {signal.confidence:.1%}\n"
            else:
                message["Subject"] = "AMA Pro Scanner: Daily Status (No Signals)"
                body = "No signals detected in today's scan."
            
            message.attach(MIMEText(body, "plain"))
            
            # Send email
            await aiosmtplib.send(
                message,
                hostname="smtp.gmail.com",
                port=465,
                username=self.config.gmail_user,
                password=self.config.gmail_password,
                use_tls=True
            )
            
            print("📧 Email notification sent")
            
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
    
    async def cleanup_old_files(self):
        """Clean up old result files"""
        import glob
        
        try:
            files = glob.glob("ama_pro_scan_results_*.csv")
            if len(files) > self.config.keep_last_results:
                # Sort by modification time
                files.sort(key=os.path.getmtime, reverse=True)
                for old_file in files[self.config.keep_last_results:]:
                    os.remove(old_file)
                    print(f"🗑️ Cleaned up: {old_file}")
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")
    
    async def run(self):
        """Main execution loop"""
        try:
            # Start dashboard in background
            dashboard_task = asyncio.create_task(self.dashboard.run())
            
            # Run scan
            await self.run_scan()
            
            # Save results
            await self.save_results()
            
            # Cleanup
            await self.cleanup_old_files()
            
            # Keep dashboard running for a bit
            await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            print("\n\n🛑 Scan interrupted by user")
        finally:
            self.dashboard.stop()
            dashboard_task.cancel()
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources"""
        print("\n🧹 Cleaning up...")
        
        # Close data fetcher
        await self.data_fetcher.close()
        
        # Stop WebSocket manager
        if self.websocket_manager:
            await self.websocket_manager.stop()
        
        # Clean up cache
        await self.cache.cleanup()
        
        print("✅ Cleanup complete")

# =============================================================================
# Main Entry Point
# =============================================================================

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="AMA Pro Scanner - High-Performance Edition")
    parser.add_argument('--exchange', type=str, default='binance', choices=['binance', 'mexc'],
                       help='Exchange to use')
    parser.add_argument('--symbols', type=int, default=500,
                       help='Number of symbols to scan')
    parser.add_argument('--timeframes', type=str, default='15m,30m,1h,2h,4h,1d',
                       help='Comma-separated timeframes')
    parser.add_argument('--concurrent', type=int, default=50,
                       help='Max concurrent symbols')
    parser.add_argument('--cache-ttl', type=int, default=30,
                       help='Cache TTL in seconds')
    parser.add_argument('--no-websocket', action='store_true',
                       help='Disable WebSocket')
    parser.add_argument('--no-ml', action='store_true',
                       help='Disable ML predictions')
    parser.add_argument('--no-redis', action='store_true',
                       help='Disable Redis')
    
    args = parser.parse_args()
    
    # Create configuration
    config = ScannerConfig(
        exchange_id=args.exchange,
        symbol_limit=args.symbols,
        timeframes=[tf.strip() for tf in args.timeframes.split(',')],
        max_concurrent_symbols=args.concurrent,
        cache_ttl_seconds=args.cache_ttl,
        use_websocket=not args.no_websocket,
        ml_enabled=not args.no_ml,
        redis_enabled=not args.no_redis
    )
    
    # Create and run scanner
    scanner = AMAProScanner(config)
    
    try:
        await scanner.initialize()
        await scanner.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Scan interrupted by user")
    finally:
        await scanner.cleanup()
    
    # Print final cache stats
    cache_stats = scanner.cache.get_stats()
    print("\n📊 Final Cache Statistics:")
    print(f"  • Memory Hit Rate: {cache_stats['memory_hit_rate']}")
    print(f"  • Redis Hit Rate: {cache_stats['redis_hit_rate']}")
    print(f"  • Memory Entries: {cache_stats['memory_entries']}")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())