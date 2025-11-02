from bot import main
import logging
from flask import Flask
import threading
import os

# Configure basic logging for main.py
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app for health checks
app = Flask(__name__)

@app.route('/')
def health_check():
    """Health check endpoint for Render and external monitoring"""
    return {
        "status": "healthy",
        "service": "ErixCast Bot",
        "version": "1.0.0",
        "uptime": "active"
    }, 200

@app.route('/ping')
def ping():
    """Simple ping endpoint"""
    return "pong", 200

def run_flask():
    """Run Flask server in a separate thread"""
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting Flask health check server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    try:
        logger.info("🚀 Starting ErixCast Bot Application...")

        # Start Flask server in background thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # Start the bot
        main()
    except Exception as e:
        logger.critical(f"💥 Application crashed: {e}")
        raise
