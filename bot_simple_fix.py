#!/usr/bin/env python3
"""
Correzione semplificata per il bot - risolve i problemi di event loop
Versione robusta e stabile per Render
"""

import os
import sys
import logging
from pathlib import Path

# Add app directory to Python path
app_dir = Path(__file__).parent / "app"
sys.path.insert(0, str(app_dir))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def create_simple_bot_main():
    """Crea una versione semplificata del main del bot"""
    
    bot_main_content = '''
def main():
    """Simplified main function to avoid event loop issues"""
    logger.info("🚀 Starting ErixCast bot (simplified version)...")
    
    import asyncio
    import sys
    
    # Simple approach - just run the bot once
    try:
        # Ensure we have a clean event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.warning("Event loop already running, stopping...")
                loop.stop()
        except:
            pass
        
        # Create fresh event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        logger.info("▶️ Starting bot main loop...")
        loop.run_until_complete(run_bot_main_loop())
        
        logger.info("✅ Bot completed successfully")
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
        # Exit cleanly to let Render restart
        sys.exit(1)
    finally:
        # Cleanup
        try:
            remove_pid_file()
            remove_lock_file()
        except:
            pass
        
        # Close event loop properly
        try:
            if not loop.is_closed():
                loop.close()
        except:
            pass

if __name__ == '__main__':
    main()
'''
    
    return bot_main_content

def apply_simple_fix():
    """Applica la correzione semplificata al bot"""
    
    logger.info("🔧 Applying simple bot fix...")
    
    # Leggi il file bot.py corrente
    bot_file = Path("app/bot.py")
    
    if not bot_file.exists():
        logger.error("❌ bot.py file not found")
        return False
    
    try:
        # Leggi il contenuto
        with open(bot_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Trova e sostituisci la funzione main
        import re
        
        # Pattern per trovare la funzione main
        main_pattern = r'def main\(\):.*?(?=\n\ndef|\n\nif __name__|\Z)'
        
        # Nuova funzione main semplificata
        new_main = '''def main():
    """Simplified main function to avoid event loop issues"""
    logger.info("🚀 Starting ErixCast bot (simplified version)...")
    
    import asyncio
    import sys
    
    # Simple approach - just run the bot once
    try:
        # Create fresh event loop
        try:
            # Close any existing loop
            try:
                old_loop = asyncio.get_event_loop()
                if not old_loop.is_closed():
                    old_loop.close()
            except:
                pass
            
            # Create new loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        except Exception as loop_e:
            logger.warning(f"Event loop setup warning: {loop_e}")
            # Fallback - use default loop
            loop = asyncio.get_event_loop()
        
        logger.info("▶️ Starting bot main loop...")
        loop.run_until_complete(run_bot_main_loop())
        
        logger.info("✅ Bot completed successfully")
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
        # Exit cleanly to let Render restart
        sys.exit(1)
    finally:
        # Cleanup
        try:
            remove_pid_file()
            remove_lock_file()
        except:
            pass'''
        
        # Sostituisci la funzione main
        new_content = re.sub(main_pattern, new_main, content, flags=re.DOTALL)
        
        # Scrivi il file aggiornato
        with open(bot_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        logger.info("✅ Simple bot fix applied successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to apply simple fix: {e}")
        return False

def main():
    """Funzione principale"""
    logger.info("🔧 ErixCast Bot Simple Fix")
    logger.info("=" * 40)
    
    if apply_simple_fix():
        logger.info("✅ Fix applied successfully!")
        logger.info("🚀 Bot should now start without event loop issues")
    else:
        logger.error("❌ Fix failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()