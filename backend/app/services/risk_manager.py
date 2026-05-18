class RiskManager:
    def __init__(self, risk_per_trade_percent=1.0, account_size=100000):
        self.risk_percent = risk_per_trade_percent
        self.account_size = account_size

    def calculate_trade_parameters(self, entry_price: float, atr: float, bias: str):
        # Professional standard: 1.5x ATR for Stop Loss, 3x ATR for Take Profit
        risk_points = atr * 1.5
        reward_points = atr * 3.0
        
        if bias.lower() == 'bullish':
            sl = entry_price - risk_points
            tp = entry_price + reward_points
        elif bias.lower() == 'bearish':
            sl = entry_price + risk_points
            tp = entry_price - reward_points
        else:
            return None

        # Position Sizing Logic
        risk_amount = self.account_size * (self.risk_percent / 100)
        qty = int(risk_amount / risk_points) if risk_points > 0 else 0
            
        return {
            "entry": round(entry_price, 2),
            "stop_loss": round(sl, 2),
            "take_profit": round(tp, 2),
            "qty": qty,
            "risk_reward_ratio": round(reward_points / risk_points, 2),
            "risk_amount": round(risk_amount, 2)
        }
