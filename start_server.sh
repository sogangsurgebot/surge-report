#!/bin/bash
# Start the YouTube Analyzer API Server
# Requires: yt-dlp, Python 3.8+, fastapi, uvicorn

echo "Starting YouTube Insight Analyzer API Server..."
echo "Server will run on http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

# Check if yt-dlp is installed
if ! command -v yt-dlp &> /dev/null; then
    echo "Error: yt-dlp is not installed"
    echo "Please install yt-dlp first: pip install yt-dlp"
    exit 1
fi

cd /root/.openclaw/workspace/surge-report
python3 api_server.py
