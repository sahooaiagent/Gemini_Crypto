# Gemini Crypto Scanner Terminal

A powerful cryptocurrency market scanner powered by **Binance** and faithful to the **AMA PRO TEMA** logic.

## 🚀 Quick Start

### 1. Prerequisites
Make sure you have Python 3.9+ installed.

### 2. Setup
Check out the `Gemini_Crypto` folder:
```bash
cd Gemini_Crypto
```

### 3. Run Backend (FastAPI)
The backend serves the crypto dashboard automatically.

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
python3 main.py
```

### 4. Access the Dashboard
Once the server is running, open your browser and go to:
**[http://localhost:8001](http://localhost:8001)**

---

## 🛠 Features
- **Binance Integration:** Real-time data for Top 20-500 coins by volume.
- **Perpetual Support:** Scan both Spot and USDT-Margined Perpetual contracts.
- **Strict Logic:** Validates signals on the immediate previous closed candle (index -2).
- **Adaptive TEMA:** Automatically adjusts Fast/Slow periods based on timeframe.
- **Enterprise UI:** Real-time crypto heatmap, ticker tape, and TradingView charting.
