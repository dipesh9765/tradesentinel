"""
Root Backward-Compatibility Shim for TradeSentinel FastAPI Server.
Delegates cleanly to the modular enterprise application package `app.main`.
"""

from app.main import app, create_app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
