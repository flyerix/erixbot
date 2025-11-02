from bot import main
import logging

# Configure basic logging for main.py
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    try:
        logger.info("🚀 Starting ErixCast Bot Application...")
        main()
    except Exception as e:
        logger.critical(f"💥 Application crashed: {e}")
        raise
