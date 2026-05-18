from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.websockets import router as ws_router
from app.api.analysis import router as analysis_router
from app.core.config import settings
from app.core.db import init_db
from app.services.market_data import MarketDataEngine, NSEPoller
from contextlib import asynccontextmanager
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    
    # Capture the running event loop and store it for threadsafe broadcasts
    from app.services.market_data import set_main_loop
    set_main_loop(asyncio.get_running_loop())
    
    # Dhan feed (skipped if no subscription)
    engine = MarketDataEngine()
    engine.start()
    
    # NSE Live Poller (primary price source, free)
    poller = NSEPoller()
    poller.start()
    
    yield

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # Fix CORS error with allow_credentials
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router, prefix="/api")
app.include_router(analysis_router, prefix="/api/analysis")

@app.get("/")
def read_root():
    return {"status": "ok", "message": f"{settings.PROJECT_NAME} Backend Running with Dhan API"}

# In a real scenario, we'd start background tasks here for MarketDataEngine.
