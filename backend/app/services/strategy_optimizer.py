import os
import json
from sqlalchemy.future import select
from app.models.market import TradeModel
from app.core.db import SessionLocal

PARAMS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "strategy_params.json")

class StrategyOptimizer:
    """
    Self-Learning Machine Learning Engine (Option 3).
    Analyzes historical PnL of closed trades from Supabase and optimizes
    the entry thresholds of HighProbabilityStrategy dynamically (Reinforcement style policy search).
    """

    @staticmethod
    def load_params():
        try:
            if os.path.exists(PARAMS_FILE):
                with open(PARAMS_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading strategy parameters: {e}")
        
        # Fallback to default parameters
        return {
            "pcr_bullish_threshold": 1.1,
            "pcr_bearish_threshold": 0.9,
            "rsi_bullish_threshold": 50,
            "rsi_bearish_threshold": 50
        }

    @staticmethod
    def save_params(params):
        try:
            with open(PARAMS_FILE, "w") as f:
                json.dump(params, f, indent=2)
            print(f"Strategy Optimizer: Successfully saved optimized parameters: {params}")
        except Exception as e:
            print(f"Error saving strategy parameters: {e}")

    @classmethod
    async def optimize_strategy(cls):
        """
        Background Reinforcement loop.
        Analyzes trade history from Supabase and adjusts the PCR and RSI rules.
        """
        print("Strategy Optimizer: Initiating self-learning optimization loop...")
        
        async with SessionLocal() as db:
            # Fetch last 20 closed trades from Supabase database
            result = await db.execute(
                select(TradeModel)
                .filter(TradeModel.status == "CLOSED")
                .order_by(TradeModel.entry_time.desc())
                .limit(20)
            )
            trades = result.scalars().all()

        if len(trades) < 3:
            print(f"Strategy Optimizer: Only {len(trades)} closed trades found. Need at least 3 trades for ML optimization.")
            return

        params = cls.load_params()
        
        ce_trades = [t for t in trades if t.direction == "CE"]
        pe_trades = [t for t in trades if t.direction == "PE"]

        # Calculate Win-Rate and Average PnL for CE (Bullish) trades
        ce_wins = [t for t in ce_trades if float(t.pnl) > 0]
        ce_losses = [t for t in ce_trades if float(t.pnl) <= 0]
        
        # Calculate Win-Rate and Average PnL for PE (Bearish) trades
        pe_wins = [t for t in pe_trades if float(t.pnl) > 0]
        pe_losses = [t for t in pe_trades if float(t.pnl) <= 0]

        adjustments_made = []

        # ─── Banish Lossy CE entries by raising PCR Bullish Threshold ───
        if len(ce_trades) >= 2:
            ce_win_rate = len(ce_wins) / len(ce_trades)
            if ce_win_rate < 0.40:
                # CE trades have poor win rate. Make entry criteria more strict!
                old_pcr = params["pcr_bullish_threshold"]
                params["pcr_bullish_threshold"] = min(1.4, round(params["pcr_bullish_threshold"] + 0.05, 2))
                params["rsi_bullish_threshold"] = min(60, params["rsi_bullish_threshold"] + 2)
                adjustments_made.append(f"CE Win-Rate low ({ce_win_rate:.0%}). Tightened Bullish rules: PCR threshold {old_pcr} -> {params['pcr_bullish_threshold']}.")
            elif ce_win_rate > 0.70:
                # Highly successful! Can slightly ease rules to capture more trades
                old_pcr = params["pcr_bullish_threshold"]
                params["pcr_bullish_threshold"] = max(1.05, round(params["pcr_bullish_threshold"] - 0.02, 2))
                params["rsi_bullish_threshold"] = max(45, params["rsi_bullish_threshold"] - 1)
                adjustments_made.append(f"CE Win-Rate high ({ce_win_rate:.0%}). Expanded Bullish criteria: PCR threshold {old_pcr} -> {params['pcr_bullish_threshold']}.")

        # ─── Banish Lossy PE entries by lowering PCR Bearish Threshold ───
        if len(pe_trades) >= 2:
            pe_win_rate = len(pe_wins) / len(pe_trades)
            if pe_win_rate < 0.40:
                # PE trades have poor win rate. Make bearish criteria stricter!
                old_pcr = params["pcr_bearish_threshold"]
                params["pcr_bearish_threshold"] = max(0.6, round(params["pcr_bearish_threshold"] - 0.05, 2))
                params["rsi_bearish_threshold"] = max(40, params["rsi_bearish_threshold"] - 2)
                adjustments_made.append(f"PE Win-Rate low ({pe_win_rate:.0%}). Tightened Bearish rules: PCR threshold {old_pcr} -> {params['pcr_bearish_threshold']}.")
            elif pe_win_rate > 0.70:
                # Highly successful! Can expand PE entries
                old_pcr = params["pcr_bearish_threshold"]
                params["pcr_bearish_threshold"] = min(0.95, round(params["pcr_bearish_threshold"] + 0.02, 2))
                params["rsi_bearish_threshold"] = min(55, params["rsi_bearish_threshold"] + 1)
                adjustments_made.append(f"PE Win-Rate high ({pe_win_rate:.0%}). Expanded Bearish criteria: PCR threshold {old_pcr} -> {params['pcr_bearish_threshold']}.")

        if adjustments_made:
            cls.save_params(params)
            print(f"Strategy Optimizer Adjustments:\n" + "\n".join([f"- {a}" for a in adjustments_made]))
        else:
            print("Strategy Optimizer: Strategy parameters are already fully optimized for current performance.")
