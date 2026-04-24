"""Integral Trading — FastAPI"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import backtest, strategies, positions, scanner

app = FastAPI(title="Integral Trading API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])
app.include_router(backtest.router,   prefix="/backtest",   tags=["Backtest"])
app.include_router(positions.router,  prefix="/positions",  tags=["Positions"])
app.include_router(scanner.router,    prefix="/scanner",    tags=["Scanner"])

@app.get("/")
def root():   return {"status": "ok", "app": "Integral Trading", "version": "0.1.0"}

@app.get("/health")
def health(): return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=True)
