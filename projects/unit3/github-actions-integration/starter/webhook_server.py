#!/usr/bin/env python3
"""
Simple webhook server for GitHub Actions events.
Stores events in a JSON file that the MCP server can read.
"""

import json
from datetime import datetime
from pathlib import Path
from aiohttp import web
from pprint import pprint

# File to store events
EVENTS_FILE = Path(__file__).parent / "github_events.json"

async def handle_webhook(request):
    """Handle incoming GitHub webhook"""
    print("Webhook received")
    try:
        # First, read the raw body as text to see what we're getting
        body = await request.text()
        print("--- Raw Request Body ---")
        print(body)
        print("------------------------")

        # Now, try to parse it as JSON
        data = json.loads(body)
        pprint(data)
        
        # Create event record
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": request.headers.get("X-GitHub-Event", "unknown"),
            "payload": data
        }
        pprint(event)
        
        # Load existing events
        events = []
        if EVENTS_FILE.exists():
            with open(EVENTS_FILE, 'r') as f:
                events = json.load(f)
        
        # Add new event and keep last 100
        events.append(event)
        events = events[-100:]
        
        # Save events
        with open(EVENTS_FILE, 'w') as f:
            json.dump(events, f, indent=2)
        
        return web.json_response({"status": "received"})
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        print("This likely means the request body was empty or not valid JSON.")
        return web.json_response({"error": f"JSON Decode Error: {e}", "body_received": body}, status=400)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return web.json_response({"error": str(e)}, status=400)

# Create app and add route
app = web.Application()
app.router.add_post('/webhook/github', handle_webhook)

if __name__ == '__main__':
    print("🚀 Starting webhook server on http://localhost:8080")
    print("📝 Events will be saved to:", EVENTS_FILE)
    print("🔗 Webhook URL: http://localhost:8080/webhook/github")
    web.run_app(app, host='localhost', port=8080)