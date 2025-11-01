#!/usr/bin/env python3
"""Run the FastAPI backend server."""
import os
import sys
import uvicorn
from pathlib import Path

def main():
    """Start the server after checking database exists."""
    # Check if database exists
    db_path = os.getenv("DB_PATH", "./data/youglish.db")
    if not Path(db_path).exists():
        print("⚠ Database not found. Initializing...")
        from init_db import init_database
        init_database()
    
    print("Starting YouGlish-lite API server...")
    print("Server will be available at: http://localhost:8000")
    print("API docs at: http://localhost:8000/docs")
    print("\nPress CTRL+C to stop the server\n")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped")
        sys.exit(0)

