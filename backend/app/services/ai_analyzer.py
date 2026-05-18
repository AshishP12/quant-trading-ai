import openai
from datetime import datetime
from app.core.config import settings

class AIAnalyzer:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        if self.api_key:
            self.client = openai.AsyncOpenAI(api_key=self.api_key)

    def _generate_fallback_insight(self, symbol: str, chain_data: dict, current_price: float) -> str:
        import random
        from datetime import datetime

        pcr = chain_data.get('pcr', 1.0)
        max_pain = chain_data.get('max_pain', current_price)
        highest_ce = chain_data.get('highest_ce_strike', current_price + 300)
        highest_pe = chain_data.get('highest_pe_strike', current_price - 300)
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        price_vs_pain = current_price - max_pain
        atm = round(current_price / 50) * 50

        # Market session context
        hour = now.hour
        minute = now.minute
        
        # Check for market close first
        if hour >= 15 and minute >= 30 or hour > 15:
            session = "market_close"
            session_note = f"Market close ho chuka hai. Aaj ka din bhar ka settlement {atm} ATM ke paas hua. Kal ke liye gap up/down setup pe focus karein. Abhi koi nayi entry NAHI karni hai."
        elif hour < 10:
            session = "opening"
            session_note = "Opening ghante mein volatility zyada hoti hai, tight SL ke bina entry NAHI karni chahiye."
        elif hour < 12:
            session = "mid-morning"
            session_note = "Mid-morning mein trend confirm hota hai, pullback pe entry kar sakte hain."
        elif hour < 14:
            session = "afternoon"
            session_note = f"Dophar ke session mein {atm} ATM ke aas paas consolidation dekha ja raha hai. Breakout ka wait karein."
        else:
            session = "closing"
            session_note = "Closing ke paas positions unwind hoti hain, Max Pain ki taraf kheenchav aata hai. High risk zone, quantity kam rakhein."

        # Price vs Max Pain analysis
        if abs(price_vs_pain) < 50:
            pain_note = f"Price {current_price:.0f} bilkul Max Pain {max_pain:.0f} ke paas hai — market neutral zone mein hai."
        elif price_vs_pain > 0:
            pain_note = f"Price {current_price:.0f}, Max Pain {max_pain:.0f} se {price_vs_pain:.0f} pts UPAR hai — option sellers ko pressure aa sakta hai."
        else:
            pain_note = f"Price {current_price:.0f}, Max Pain {max_pain:.0f} se {abs(price_vs_pain):.0f} pts NICHE hai — bulls ko defend karna hoga."

        # PCR-based bias with variety
        if pcr > 1.3:
            bias_lines = [
                f"PCR {pcr:.2f} strong bullish signal de raha hai. {highest_pe:.0f} PE par heavy writing hai — yahi support hai. CE buyers ke liye ENTRY banti hai. {pain_note}",
                f"[{time_str}] PCR {pcr:.2f} — institutions Put likh rahe hain matlab unhe neeche nahi jaane dena. {highest_pe:.0f} ka support strong hai. Dips par ENTRY kar sakte hain. {session_note}",
                f"Bullish bias banta hai: PCR {pcr:.2f}, {highest_pe:.0f} par Put wall solid hai. Agar {highest_pe:.0f} hold kare toh {atm+100:.0f} CE mein ENTRY consider kar sakte hain. {pain_note}",
            ]
        elif pcr < 0.8:
            bias_lines = [
                f"PCR {pcr:.2f} — Call writers dominant hain. {highest_ce:.0f} par strong resistance hai. PE buyers ke liye ENTRY opportunity ho sakti hai. {pain_note}",
                f"[{time_str}] Bearish setup dikh raha hai — PCR {pcr:.2f}, {highest_ce:.0f} CE par massive OI. Bulls ko yahan resistance milega. Bounce par PE mein ENTRY karein. {session_note}",
                f"Market ke upar jaane ki koshish toot rahi hai: {highest_ce:.0f} par Call wall strong hai. PE trade mein ENTRY le sakte hain, risk-reward acha hai. {pain_note}",
            ]
        else:
            bias_lines = [
                f"[{time_str}] PCR {pcr:.2f} — market range-bound hai. {highest_pe:.0f} support aur {highest_ce:.0f} resistance ke beech price ghoom raha hai. Abhi ENTRY NAHI karni hai. {session_note}",
                f"Mixed signals: PCR {pcr:.2f} neutral zone mein hai. {atm:.0f} ATM ke aas paas consolidation hai. {pain_note} Abhi koi nayi ENTRY mat lo, wait karo.",
                f"Sideways market: {highest_pe:.0f}–{highest_ce:.0f} range mein price stuck hai. Abhi clear trend NAHI hai isliye ENTRY avoid karein. {session_note}",
            ]

        # For market close, override the message to show end of day insight
        if hour >= 15 and minute >= 30 or hour > 15:
            return f"[{time_str}] {session_note} Aaj ka data summary: PCR {pcr:.2f}, aur Max Pain {max_pain:.0f} tha. Kal market conditions reassess karein."

        return random.choice(bias_lines)


    async def analyze_option_chain(self, symbol: str, chain_data: dict, current_price: float):
        # Fetch last 5 closed trades from Supabase database for dynamic self-learning feedback (Option 2)
        from app.core.db import SessionLocal
        from app.models.market import TradeModel
        from sqlalchemy.future import select
        
        trade_feedback = ""
        try:
            async with SessionLocal() as db:
                res = await db.execute(
                    select(TradeModel)
                    .filter(TradeModel.status == "CLOSED")
                    .order_by(TradeModel.entry_time.desc())
                    .limit(5)
                )
                past_trades = res.scalars().all()
                if past_trades:
                    trade_feedback = "\nUser's Recent Trade Performance Feedback (Supabase History):\n"
                    for t in past_trades:
                        trade_feedback += f"- Direction: {t.direction}, Strike: {t.strike}, Qty: {t.qty}, PnL: {float(t.pnl)}, Reason: {t.reason or 'Manual Exit'}\n"
                    trade_feedback += "\nTask: Use this performance data as active learning feedback. Critique any bad habits (e.g. overtrading, exiting too early, taking high-risk PE trades in a bullish market) and suggest adjustments. Adapt your daily guidance to prevent repeating past mistakes.\n"
        except Exception as e:
            print(f"AI Analyzer: Error loading past trades for feedback loop: {e}")

        if not self.api_key:
            return self._generate_fallback_insight(symbol, chain_data, current_price)

        prompt = f"""
        You are an elite Hedge Fund Options Trader. Analyze the Option Chain data for {symbol} trading at {current_price}.
        The current time is {datetime.now().strftime("%H:%M")}.
        
        Data Context:
        - PCR (Put Call Ratio): {chain_data['pcr']}
        - Max Pain Strike: {chain_data['max_pain']}
        - Highest Call OI Strike (Resistance): {chain_data['highest_ce_strike']}
        - Highest Put OI Strike (Support): {chain_data['highest_pe_strike']}
        {trade_feedback}
        Provide a concise (max 3 sentences) market insight in Hinglish (Hindi + English mix).
        Follow these rules strictly:
        1. If time is 15:30 or later, provide an End of Day (Market Close) Summary.
        2. Otherwise, clearly state whether a trader should make an ENTRY right now or WAIT based on the setup and the feedback above. 
        Focus strictly on institutional bias, trap zones, and short covering potential. Keep the tone practical.
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a professional quant trader."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=180,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            # print(f"OpenAI API Error: {str(e)}")
            # If 429 Insufficient Quota or any other error occurs, fall back automatically!
            return self._generate_fallback_insight(symbol, chain_data, current_price)
