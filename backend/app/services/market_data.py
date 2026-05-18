import asyncio
import json
import threading
import time
import requests
from app.core.config import settings

# Store a reference to the main FastAPI event loop for cross-thread broadcasting
_main_loop: asyncio.AbstractEventLoop | None = None

def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Called from main.py lifespan to store the running event loop."""
    global _main_loop
    _main_loop = loop
    print("Main event loop captured for threadsafe broadcasting.")

async def broadcast_from_main(payload: str):
    from app.api.websockets import manager
    await manager.broadcast(payload)

def broadcast_threadsafe(payload: str):
    if _main_loop and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast_from_main(payload), _main_loop)
    else:
        print("Warning: main loop not ready yet, tick dropped.")


# ── Dhan Market Feed (requires paid subscription) ─────────────────────────────
class MarketDataEngine:
    def __init__(self):
        self.client_id = settings.DHAN_CLIENT_ID
        self.access_token = settings.DHAN_ACCESS_TOKEN
        self._started = False

    def start(self):
        # Dhan Market Feed subscription is required for WebSocket ticks.
        # If not subscribed, we skip silently — NSEPoller handles live prices.
        if not self.client_id or not self.access_token:
            print("Dhan credentials missing. Using NSE Poller only.")
            return
        print("Dhan Market Feed subscription not active — using NSE Poller for live prices.")


# ── NSE Live Poller (FREE - No subscription required) ─────────────────────────
class NSEPoller:
    """
    Polls NSE public APIs every 3 seconds for live Nifty price.
    Broadcasts ticks to all connected frontend WebSocket clients.
    No API key or subscription needed!
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/",
    }

    def __init__(self):
        self._session = requests.Session()
        self._running = False
        self._last_price = None
        # Warm up session (NSE requires a browser-like session with cookies)
        self._init_session()

    def _init_session(self):
        try:
            self._session.get("https://www.nseindia.com", headers=self.HEADERS, timeout=8)
            print("NSE session initialized.")
        except Exception as e:
            print(f"NSE session init warning: {e}")

    def _fetch_nifty_price(self) -> float | None:
        """Try multiple NSE endpoints to get Nifty LTP."""
        # Method 1: allIndices API
        try:
            r = self._session.get(
                "https://www.nseindia.com/api/allIndices",
                headers=self.HEADERS, timeout=6
            )
            if r.status_code == 200:
                for idx in r.json().get("data", []):
                    if idx.get("index") == "NIFTY 50":
                        price = float(idx["last"])
                        print(f"NSE Tick → Nifty: {price}")
                        return price
        except Exception:
            pass

        # Method 2: Market status API as backup
        try:
            r = self._session.get(
                "https://www.nseindia.com/api/marketStatus",
                headers=self.HEADERS, timeout=6
            )
            if r.status_code == 200:
                data = r.json()
                # Re-init session if blocked and retry allIndices
                self._init_session()
        except Exception:
            pass

        return None

    def start(self):
        self._running = True
        t = threading.Thread(target=self._poll_loop, daemon=True, name="NSEPollerThread")
        t.start()
        print("NSE Live Poller started — Nifty price updates every 3 seconds.")

    def _poll_loop(self):
        time.sleep(3)  # Wait for main loop to be ready
        re_init_counter = 0

        while self._running:
            price = self._fetch_nifty_price()

            if price:
                self._last_price = price
                tick = json.dumps({
                    "instrument_token": "13",
                    "security_id": "13",
                    "last_price": price,
                    "source": "nse_live"
                })
                broadcast_threadsafe(tick)
                re_init_counter = 0
            else:
                re_init_counter += 1
                # If 3 consecutive failures, re-initialize NSE session
                if re_init_counter >= 3:
                    print("NSE blocked — re-initializing session...")
                    self._init_session()
                    re_init_counter = 0

            time.sleep(3)  # Poll every 3 seconds for smooth chart updates
