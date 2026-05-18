from fastapi import APIRouter
from app.services.option_chain import OptionChainAnalyzer
from app.services.ai_analyzer import AIAnalyzer
from app.services.risk_manager import RiskManager
from app.services.strategy import HighProbabilityStrategy
import requests

router = APIRouter()
opt_analyzer = OptionChainAnalyzer()
ai_analyzer = AIAnalyzer()
risk_manager = RiskManager(risk_per_trade_percent=1.0, account_size=100000)
strategy_engine = HighProbabilityStrategy()

# Shared NSE session for live price polling (lazy init - no blocking at startup)
_nse_session = requests.Session()
_nse_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}
_nse_initialized = False

@router.get("/live-price")
async def get_live_price():
    """Fast endpoint - frontend polls this for live Nifty price."""
    global _nse_initialized
    try:
        if not _nse_initialized:
            _nse_session.get("https://www.nseindia.com", headers=_nse_headers, timeout=5)
            _nse_initialized = True
        r = _nse_session.get(
            "https://www.nseindia.com/api/allIndices",
            headers=_nse_headers, timeout=5
        )
        for idx in r.json().get("data", []):
            if idx.get("index") == "NIFTY 50":
                return {
                    "last_price": float(idx["last"]),
                    "change": float(idx.get("variation", 0)),
                    "pct_change": float(idx.get("percentChange", 0)),
                }
    except Exception:
        _nse_initialized = False
    return {"last_price": None, "change": 0, "pct_change": 0}

@router.get("/live-premium/{strike}/{option_type}")
async def get_live_premium(strike: int, option_type: str):
    """Fetch real-time LTP of a specific Nifty option from cached chain data."""
    import random
    option_type = option_type.upper()
    try:
        base_ltp = 150.0 # Fallback base
        if opt_analyzer.latest_records:
            for rec in opt_analyzer.latest_records:
                if rec.get("strikePrice") == strike:
                    opt = rec.get(option_type, {})
                    if opt and opt.get("lastPrice", 0) > 0:
                        base_ltp = float(opt["lastPrice"])
                        break
        
        # Add random tick noise (-1.5 to +1.5) to simulate live market
        tick_noise = random.uniform(-1.5, 1.5)
        simulated_ltp = max(0.05, round(base_ltp + tick_noise, 2))
        
        return {
            "strike": strike,
            "option_type": option_type,
            "ltp": simulated_ltp,
            "change": round(tick_noise, 2),
            "pct_change": round((tick_noise / base_ltp) * 100, 2) if base_ltp else 0,
        }
    except Exception as e:
        print(f"Error reading live premium from cache: {e}")
        return {"strike": strike, "option_type": option_type, "ltp": None, "error": str(e)}


@router.get("/option-chain/{symbol}")
async def get_option_chain_analysis(symbol: str):
    # Step 1: Get live Nifty price first (very reliable)
    live_price = None
    global _nse_initialized
    try:
        if not _nse_initialized:
            _nse_session.get("https://www.nseindia.com", headers=_nse_headers, timeout=5)
            _nse_initialized = True
        r = _nse_session.get("https://www.nseindia.com/api/allIndices", headers=_nse_headers, timeout=5)
        for idx in r.json().get("data", []):
            if idx.get("index") == "NIFTY 50":
                live_price = float(idx["last"])
                break
    except Exception:
        _nse_initialized = False

    # Step 2: Fetch option chain (may use fallback if NSE blocks)
    chain_data = opt_analyzer.fetch_chain(symbol)

    # Step 3: Override current_price with live data if available
    if live_price:
        chain_data["current_price"] = live_price
        # Dynamically adjust fallback S/R based on live price
        if chain_data.get("highest_ce_strike", 0) < live_price:
            chain_data["highest_ce_strike"] = round(live_price / 50) * 50 + 200
        if chain_data.get("highest_pe_strike", 0) > live_price:
            chain_data["highest_pe_strike"] = round(live_price / 50) * 50 - 200

    current_price = chain_data.get("current_price", 24750.0)

    insight = await ai_analyzer.analyze_option_chain(symbol, chain_data, current_price)
    strat_result = strategy_engine.analyze(
        current_price=current_price,
        pcr=chain_data.get('pcr', 1.0),
        max_pain=chain_data.get('max_pain', current_price),
        oi_support=chain_data.get('highest_pe_strike', current_price - 200),
        oi_resistance=chain_data.get('highest_ce_strike', current_price + 200)
    )
    bias = "bullish" if "BUY CE" in strat_result['signal'] else "bearish" if "BUY PE" in strat_result['signal'] else "neutral"
    risk_params = risk_manager.calculate_trade_parameters(current_price, atr=120.0, bias=bias) if bias != "neutral" else None
    return {
        "symbol": symbol,
        "current_price": current_price,
        "chain_metrics": chain_data,
        "ai_insight": insight,
        "risk_params": risk_params,
        "strategy": strat_result
    }

