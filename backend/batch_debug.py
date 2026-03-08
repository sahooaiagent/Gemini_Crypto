"""
Batch scan: Top 20 cryptos across 15min, 30min, 2hr, 4hr
Outputs all longValid/shortValid signals found per symbol/timeframe.
"""
import asyncio
import sys
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.WARNING)

from scanner import (
    exchange, fetch_binance_data, calculate_adx, calculate_atr,
    calculate_ema, calculate_tema, get_top_binance_symbols, apply_ama_pro_tema
)

TIMEFRAMES = ["15min", "30min", "2hr", "4hr"]


async def run_batch():
    print(f"\n{'='*100}")
    print(f"  BATCH SCAN — Top 20 Cryptos | Timeframes: {', '.join(TIMEFRAMES)}")
    print(f"{'='*100}\n")

    # Fetch top 20 symbols
    top_coins = await get_top_binance_symbols(limit=20)
    if not top_coins:
        print("ERROR: Could not fetch symbols")
        await exchange.close()
        return

    symbols = [c['symbol'] for c in top_coins]
    print(f"Symbols: {', '.join(symbols)}\n")

    all_results = []

    for tf in TIMEFRAMES:
        print(f"\n{'─'*100}")
        print(f"  TIMEFRAME: {tf}")
        print(f"{'─'*100}")

        tf_results = []
        for symbol in symbols:
            try:
                df = await fetch_binance_data(symbol, tf, limit=500)
                if df is None or len(df) < 200:
                    continue

                signal, angle = apply_ama_pro_tema(
                    df,
                    tf_input=tf,
                    adaptation_speed="Medium",
                    min_bars_between=3
                )

                if signal:
                    result = {
                        'symbol': symbol,
                        'tf': tf,
                        'signal': signal,
                        'angle': f"{angle:.2f}" if angle is not None else "N/A"
                    }
                    tf_results.append(result)
                    all_results.append(result)

            except Exception as e:
                print(f"  ERROR: {symbol} {tf}: {e}")

            # Small delay to respect rate limits
            await asyncio.sleep(0.05)

        if tf_results:
            print(f"\n  {'Symbol':<20} {'Signal':<8} {'Angle':<10}")
            print(f"  {'─'*38}")
            for r in tf_results:
                print(f"  {r['symbol']:<20} {r['signal']:<8} {r['angle']:<10}")
        else:
            print(f"\n  No signals found for {tf}")

    # Summary
    print(f"\n\n{'='*100}")
    print(f"  SUMMARY — ALL SIGNALS")
    print(f"{'='*100}")
    if all_results:
        print(f"\n  {'Symbol':<20} {'Timeframe':<12} {'Signal':<8} {'Angle':<10}")
        print(f"  {'─'*50}")
        for r in sorted(all_results, key=lambda x: (x['tf'], x['symbol'])):
            print(f"  {r['symbol']:<20} {r['tf']:<12} {r['signal']:<8} {r['angle']:<10}")
        print(f"\n  Total signals: {len(all_results)}")
    else:
        print("\n  No signals found across any symbol/timeframe.")

    await exchange.close()


if __name__ == "__main__":
    asyncio.run(run_batch())
