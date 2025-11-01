#!/usr/bin/env python3
"""Run the FastAPI backend server."""
import os
import sys
import socket
import uvicorn
from pathlib import Path

def find_available_port(start_port=8000, max_attempts=100):
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find an available port in range {start_port}-{start_port + max_attempts}")

def write_frontend_env(port):
    """Write the API port to frontend .env.local file."""
    frontend_dir = Path(__file__).parent.parent / "frontend"
    if frontend_dir.exists():
        env_file = frontend_dir / ".env.local"
        try:
            env_file.write_text(f"VITE_API=http://localhost:{port}\n")
            print(f"✓ Updated frontend config to use port {port}")
        except Exception as e:
            print(f"⚠ Could not write frontend config: {e}")

def main():
    """Start the server after checking database exists."""
    # Check if database exists
    db_path = os.getenv("DB_PATH", "./data/youglish.db")
    if not Path(db_path).exists():
        print("⚠ Database not found. Initializing...")
        from init_db import init_database
        init_database()
    
    # Find an available port
    port = find_available_port(start_port=8000)
    
    # Write port to frontend config
    write_frontend_env(port)
    
    # Check cookie configuration
    cookies_browser = os.getenv("COOKIES_FROM_BROWSER", "chrome")
    
    print("Starting YouGlish-lite API server...")
    print(f"Server will be available at: http://localhost:{port}")
    print(f"API docs at: http://localhost:{port}/docs")
    print(f"YouTube cookies from: {cookies_browser}")
    print("\n💡 Tip: Make sure you're logged into YouTube in {cookies_browser}".format(cookies_browser=cookies_browser.capitalize()))
    print("   See YOUTUBE_COOKIE_SETUP.md for help with YouTube bot detection")
    print("\n⚠ If your frontend is already running, restart it to use the new port")
    print("\nPress CTRL+C to stop the server\n")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped")
        sys.exit(0)

