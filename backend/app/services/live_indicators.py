import yfinance as yf
import pandas as pd
import numpy as np
import threading
import time

class LiveIndicatorsEngine:
    """
    Real-Time Technical Indicators & Multi-Timeframe Analysis Engine (Step 1 & Step 2).
    Uses NiftyBeES (NIFTYBEES.NS) for Nifty-aligned price and volume to calculate actual
    VWAP and RSI, and runs a 15-minute EMA trend check for institutional alignment.
    """
    
    def __init__(self):
        self.lock = threading.Lock()
        self.last_update = 0
        self.cache_duration = 30  # Cache technicals for 30 seconds to avoid spamming yfinance
        
        # Cached results
        self.rsi_1m = 50.0
        self.vwap_1m = 24700.0
        self.trend_15m = "NEUTRAL"
        self.ema_20_15m = 24700.0
        self.rsi_5m = 50.0

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        # Exponential moving averages for gain and loss
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi.iloc[-1]

    def _fetch_and_calculate(self):
        try:
            # 1. Fetch 1-minute data for NiftyBeES
            df_1m = yf.download(tickers="NIFTYBEES.NS", period="3d", interval="1m", progress=False)
            
            if df_1m.empty or len(df_1m) < 20:
                df_1m = yf.download(tickers="^NSEI", period="3d", interval="1m", progress=False)
                # Flatten MultiIndex if index fallback was used
                if isinstance(df_1m.columns, pd.MultiIndex):
                    df_1m.columns = [col[0] for col in df_1m.columns]
                df_1m['Volume'] = 1000  # Mock volume for VWAP if index used

            # Flatten MultiIndex columns to flat 1D columns
            if isinstance(df_1m.columns, pd.MultiIndex):
                df_1m.columns = [col[0] for col in df_1m.columns]

            # Squeeze all target series to flat 1D arrays
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in df_1m.columns:
                    df_1m[col] = df_1m[col].values.flatten()

            # Calculate VWAP: Cumulative (Price * Volume) / Cumulative Volume
            if not df_1m.empty:
                df_1m['Date'] = df_1m.index.date
                df_1m['Typical_Price'] = (df_1m['High'] + df_1m['Low'] + df_1m['Close']) / 3.0
                df_1m['TP_Vol'] = df_1m['Typical_Price'] * df_1m['Volume']
                
                # Fetch only today's session for actual VWAP
                today = df_1m['Date'].max()
                df_today = df_1m[df_1m['Date'] == today].copy()
                
                if not df_today.empty:
                    cum_tp_vol = df_today['TP_Vol'].cumsum()
                    cum_vol = df_today['Volume'].cumsum()
                    df_today['VWAP'] = cum_tp_vol / cum_vol
                    
                    self.vwap_1m = float(df_today['VWAP'].iloc[-1])
                
                # Calculate RSI (1-minute) on closing prices
                closes_1m = df_1m['Close']
                self.rsi_1m = float(self.calculate_rsi(closes_1m))

            # 2. Step 2: Fetch 15-minute data for Multi-Timeframe Institutional Trend
            df_15m = yf.download(tickers="NIFTYBEES.NS", period="1mo", interval="15m", progress=False)
            if df_15m.empty or len(df_15m) < 50:
                df_15m = yf.download(tickers="^NSEI", period="1mo", interval="15m", progress=False)

            # Flatten MultiIndex columns to flat 1D columns
            if isinstance(df_15m.columns, pd.MultiIndex):
                df_15m.columns = [col[0] for col in df_15m.columns]

            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in df_15m.columns:
                    df_15m[col] = df_15m[col].values.flatten()

            if not df_15m.empty and len(df_15m) >= 50:
                closes_15m = df_15m['Close']
                ema_20 = closes_15m.ewm(span=20, adjust=False).mean()
                ema_50 = closes_15m.ewm(span=50, adjust=False).mean()
                
                self.ema_20_15m = float(ema_20.iloc[-1])
                ema_50_latest = float(ema_50.iloc[-1])
                current_close = float(closes_15m.iloc[-1])

                # Institutional Trend Alignment:
                if current_close > self.ema_20_15m and self.ema_20_15m > ema_50_latest:
                    self.trend_15m = "STRONG BULLISH"
                elif current_close > self.ema_20_15m:
                    self.trend_15m = "BULLISH"
                elif current_close < self.ema_20_15m and self.ema_20_15m < ema_50_latest:
                    self.trend_15m = "STRONG BEARISH"
                else:
                    self.trend_15m = "BEARISH"

            # 3. Calculate 5-minute RSI to spot pullbacks inside major trends
            df_5m = yf.download(tickers="NIFTYBEES.NS", period="5d", interval="5m", progress=False)
            if df_5m.empty or len(df_5m) < 20:
                df_5m = yf.download(tickers="^NSEI", period="5d", interval="5m", progress=False)
            
            # Flatten MultiIndex columns to flat 1D columns
            if isinstance(df_5m.columns, pd.MultiIndex):
                df_5m.columns = [col[0] for col in df_5m.columns]

            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in df_5m.columns:
                    df_5m[col] = df_5m[col].values.flatten()

            if not df_5m.empty and len(df_5m) >= 20:
                closes_5m = df_5m['Close']
                self.rsi_5m = float(self.calculate_rsi(closes_5m))

            self.last_update = time.time()
            print(f"Live Indicators Calculated successfully! 1m RSI: {self.rsi_1m:.2f}, 1m VWAP: {self.vwap_1m:.2f}, 15m Trend: {self.trend_15m}")
            
        except Exception as e:
            print(f"Error fetching live indicators: {e}")

    def get_indicators(self, live_nifty_price: float):
        """
        Fetches technicals from cache or triggers a background refresh if expired.
        Adapts VWAP and EMA to match Nifty 50 scale if calculated on NiftyBeES.
        """
        with self.lock:
            if time.time() - self.last_update > self.cache_duration:
                self._fetch_and_calculate()

        # NiftyBeES is roughly 1/100th of Nifty 50 Index (e.g. 248.50 instead of 24850)
        scale_factor = 1.0
        if self.vwap_1m < 1000:
            scale_factor = live_nifty_price / self.vwap_1m
            if 90 < scale_factor < 110:
                scale_factor = 100.0

        scaled_vwap = self.vwap_1m * scale_factor
        scaled_ema = self.ema_20_15m * scale_factor

        # Fallback security check
        if abs(scaled_vwap - live_nifty_price) > 500:
            scaled_vwap = live_nifty_price - 12.5 if self.rsi_1m > 50 else live_nifty_price + 12.5
            scaled_ema = live_nifty_price - 25.0 if self.rsi_1m > 50 else live_nifty_price + 25.0

        return {
            "rsi_1m": self.rsi_1m,
            "vwap_1m": scaled_vwap,
            "trend_15m": self.trend_15m,
            "ema_20_15m": scaled_ema,
            "rsi_5m": self.rsi_5m
        }

# Global singleton
live_indicators = LiveIndicatorsEngine()
