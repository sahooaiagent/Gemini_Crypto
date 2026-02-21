import logging
import datetime
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
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
    "scan_time": None,
    "duration": None
}

class ScanRequest(BaseModel):
    indices: List[str]
    timeframes: List[str]
    adaptation_speed: Optional[str] = "Medium"
    min_bars_between: Optional[int] = 3
    crypto_count: Optional[int] = 20
    scanner_type: Optional[str] = "ama_pro"  # 'ama_pro', 'qwen', or 'both'

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
            scanner_type=request.scanner_type
        )
        
        duration = round(time.time() - start_time, 2)
        scan_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Store in memory
        latest_scan["results"] = results
        latest_scan["scan_time"] = scan_time
        latest_scan["duration"] = duration
        
        logging.info(f"Scan completed successfully in {duration}s. Found {len(results)} signal(s).")
        return {
            "status": "success",
            "data": results,
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
        "scan_time": latest_scan["scan_time"],
        "duration": latest_scan["duration"]
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
        top_coins = await scanner.get_top_binance_symbols(limit=10)
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
