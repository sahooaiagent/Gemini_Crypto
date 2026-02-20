import yfinance as yf
import datetime
import pandas as pd

ticker = "^DJI"
print(f"Current Time: {datetime.datetime.now()}")

data = yf.download(ticker, period="1mo", interval="1wk", progress=False)
print("\n--- DJI 1 Week Data ---")
print(data.tail())

data_1d = yf.download(ticker, period="5d", interval="1d", progress=False)
print("\n--- DJI 1 Day Data ---")
print(data_1d.tail())
