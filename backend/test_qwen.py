"""Quick test: Qwen scanner on ADA/USDT:USDT @ 45min"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

from scanner import fetch_binance_data, apply_qwen_scanner, close_exchange

async def main():
    symbol = "ADA/USDT:USDT"
    tf = "45min"

    print(f"\n{'='*60}")
    print(f"  Testing Qwen Scanner: {symbol} @ {tf}")
    print(f"{'='*60}\n")

    df = await fetch_binance_data(symbol, tf, limit=500)
    if df is None:
        print("ERROR: Failed to fetch data")
        await close_exchange()
        return

    print(f"Fetched {len(df)} candles")
    print(f"Last 3 candles:")
    for i in range(-3, 0):
        row = df.iloc[i]
        ts = df.index[i]
        print(f"  [{i}] {ts} | O={row['open']:.4f} H={row['high']:.4f} L={row['low']:.4f} C={row['close']:.4f} V={row['volume']:.0f}")

    print(f"\nNote: candle[-1] is the FORMING candle (will be dropped)")
    print(f"      candle[-2] is the latest CLOSED candle (= QwenPre check)\n")

    signal, _, _ = apply_qwen_scanner(df.copy(), tf_input=tf)

    print(f"\n{'='*60}")
    if signal:
        print(f"  RESULT: {signal} signal detected (QwenPre would fire)")
    else:
        print(f"  RESULT: No signal on latest closed candle")
    print(f"{'='*60}\n")

    await close_exchange()

asyncio.run(main())
