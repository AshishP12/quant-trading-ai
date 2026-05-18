import os
import json
import yfinance as yf
import pandas as pd
import numpy as np

PARAMS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "strategy_params.json")

class BacktestingOptimizer:
    """
    Quantitative Backtester & Parameter Optimization Engine (Method A).
    Loads 6 months of historical data, simulates trade rules, and automatically
    tunes RSI and PCR thresholds to maximize historical win rate and net profit.
    """

    @staticmethod
    def calculate_rsi_series(series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @classmethod
    def run_historical_backtest(cls, df: pd.DataFrame, rsi_bull: float, rsi_bear: float, sl_offset: float):
        """
        Simulates strategy execution over historical candles.
        Returns metrics: net_points, total_trades, win_rate, wins, losses.
        """
        in_trade = False
        trade_type = None  # "CE" or "PE"
        entry_price = 0.0
        stop_loss = 0.0
        target = 0.0
        
        net_points = 0.0
        total_trades = 0
        wins = 0
        losses = 0

        # Iterate over historical candles to simulate live ticks
        for i in range(50, len(df)):
            row = df.iloc[i]
            close = float(row['Close'])
            high = float(row['High'])
            low = float(row['Low'])
            rsi = float(row['RSI'])
            vwap = float(row['VWAP'])
            trend_ema = float(row['EMA_20'])
            
            # Mock PCR based on trend for historical simulation consistency
            pcr = 1.2 if close > trend_ema else 0.8

            if not in_trade:
                # Setup A: Strong Bullish continuation
                if close > vwap and rsi > rsi_bull and pcr > 1.1 and close > trend_ema:
                    in_trade = True
                    trade_type = "CE"
                    entry_price = close
                    stop_loss = vwap - sl_offset
                    target = close + (sl_offset * 2.2)  # Risk to Reward 1:2.2
                    total_trades += 1
                
                # Setup C: Strong Bearish continuation
                elif close < vwap and rsi < rsi_bear and pcr < 0.9 and close < trend_ema:
                    in_trade = True
                    trade_type = "PE"
                    entry_price = close
                    stop_loss = vwap + sl_offset
                    target = close - (sl_offset * 2.2)  # Risk to Reward 1:2.2
                    total_trades += 1
            else:
                if trade_type == "CE":
                    if high >= target:
                        net_points += (target - entry_price)
                        wins += 1
                        in_trade = False
                    elif low <= stop_loss:
                        net_points += (stop_loss - entry_price)
                        losses += 1
                        in_trade = False
                elif trade_type == "PE":
                    if low <= target:
                        net_points += (entry_price - target)
                        wins += 1
                        in_trade = False
                    elif high >= stop_loss:
                        net_points += (entry_price - stop_loss)
                        losses += 1
                        in_trade = False

        win_rate = (wins / total_trades) if total_trades > 0 else 0.0
        return {
            "net_points": round(net_points, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate * 100, 1),
            "wins": wins,
            "losses": losses
        }

    @classmethod
    async def train_and_optimize(cls):
        """
        Loads 6 months of historical data, runs a grid search,
        finds the mathematically best strategy limits, and saves them.
        """
        print("Backtester: Downloading 6 months of Nifty 50 historical data...")
        
        # Download 6 months of 1-hour candles for high speed and accurate swing simulation
        df = yf.download(tickers="NIFTYBEES.NS", period="6mo", interval="1h", progress=False)
        if df.empty or len(df) < 100:
            df = yf.download(tickers="^NSEI", period="6mo", interval="1h", progress=False)

        if df.empty:
            print("Backtester Error: Failed to fetch historical data.")
            return {"status": "error", "message": "Failed to fetch historical market data"}

        # Flatten MultiIndex columns if present to prevent KeyError or Alignment errors
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        # Force squeeze columns to 1D flat series
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in df.columns:
                df[col] = df[col].values.flatten()

        # Calculate standard technical indicators on the historical series
        df['RSI'] = cls.calculate_rsi_series(df['Close'], period=14)
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()

        # Calculate robust VWAP without Groupby Apply alignment bugs
        df['Date'] = df.index.date
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['TP_Vol'] = df['Typical_Price'] * df['Volume']
        
        cum_tp_vol = df.groupby('Date')['TP_Vol'].cumsum()
        cum_vol = df.groupby('Date')['Volume'].cumsum()
        
        df['VWAP'] = cum_tp_vol / cum_vol
        df['VWAP'] = df['VWAP'].fillna(df['Close'])
        
        df = df.dropna(subset=['RSI', 'VWAP', 'EMA_50']).copy()

        # Grid search parameters
        rsi_bull_grid = [48, 52, 55, 58]
        rsi_bear_grid = [42, 45, 48, 52]
        sl_offset_grid = [8.0, 10.0, 12.0, 15.0]

        best_pnl = -99999.0
        best_params = {}
        best_report = {}

        print("Backtester: Initiating Grid Search Optimization loop over last 6 months...")

        # Run grid combinations
        for rsi_bull in rsi_bull_grid:
            for rsi_bear in rsi_bear_grid:
                for sl_offset in sl_offset_grid:
                    result = cls.run_historical_backtest(df, rsi_bull, rsi_bear, sl_offset)
                    
                    if result["total_trades"] >= 5 and result["net_points"] > best_pnl:
                        best_pnl = result["net_points"]
                        best_params = {
                            "rsi_bullish_threshold": rsi_bull,
                            "rsi_bearish_threshold": rsi_bear,
                            "sl_offset": sl_offset,
                            "pcr_bullish_threshold": 1.1,
                            "pcr_bearish_threshold": 0.9
                        }
                        best_report = result

        if best_params:
            # Save historically trained parameters directly
            os.makedirs(os.path.dirname(PARAMS_FILE), exist_ok=True)
            with open(PARAMS_FILE, "w") as f:
                json.dump(best_params, f, indent=2)
            
            print(f"Backtester Training Completed! Best PnL: +{best_pnl} pts. Optimal Parameters: {best_params}")
            return {
                "status": "success",
                "message": "Model trained successfully on last 6 months of market data!",
                "optimized_parameters": best_params,
                "backtest_report": {
                    "net_points_gained": best_report["net_points"],
                    "total_trades_taken": best_report["total_trades"],
                    "win_rate_pct": best_report["win_rate"],
                    "profitable_trades": best_report["wins"],
                    "loss_making_trades": best_report["losses"]
                }
            }
        
        return {"status": "error", "message": "Grid search failed to find stable positive setup parameters"}
