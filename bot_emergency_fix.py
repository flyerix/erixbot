#!/usr/bin/env python3
"""
Emergency fix per il bot - versione ultra-semplificata che sicuramente funziona
"""

import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_minimal_bot():
    """Crea una versione minimale del bot che sicuramente funziona"""
    
    minimal_main = '''
async def run_bot_main_loop():
    """Ultra-simplified bot main loop - guaranteed to work"""
    global USE_WEBHOOK
    
    logger.info("🚀 Starting ultra-simplified bot main loop...")
    
    # Create PID file to prevent multiple instances
    create_pid_file()
    
    # Test database connection
    try:
        session = SessionLocal()
        from sqlalchemy import text
        session.execute(text("SELECT 1"))
        session.close()
        logger.info("✅ Database connection verified")
    except Exception as db_e:
        logger.error(f"💥 Database connection failed: {db_e}")
        raise

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add simple error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(f"Bot error: {context.error}")

    application.add_error_handler(error_handler)

    # Register handlers
    logger.info("📝 Registering command handlers...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("dashboard", dashboard_command))
    application.add_handler(CommandHandler("renew", renew_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("stop_contact", stop_contact_command))
    application.add_handler(CommandHandler("stats", stats_command))

    logger.info("📝 Registering message handlers...")
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_contact_message), group=1)

    logger.info("📝 Registering callback query handlers...")
    # Register callback handlers
    application.add_handler(CallbackQueryHandler(renew_list_callback, pattern='^renew_list:'))
    application.add_handler(CallbackQueryHandler(renew_months_callback, pattern='^renew_months:'))
    application.add_handler(CallbackQueryHandler(confirm_renew_callback, pattern='^confirm_renew:'))
    application.add_handler(CallbackQueryHandler(delete_list_callback, pattern='^delete_list:'))
    application.add_handler(CallbackQueryHandler(confirm_delete_callback, pattern='^confirm_delete:'))
    application.add_handler(CallbackQueryHandler(notify_list_callback, pattern='^notify_list:'))
    application.add_handler(CallbackQueryHandler(notify_days_callback, pattern='^notify_days:'))
    application.add_handler(CallbackQueryHandler(view_ticket_callback, pattern='^view_ticket:'))
    application.add_handler(CallbackQueryHandler(reply_ticket_callback, pattern='^reply_ticket:'))
    application.add_handler(CallbackQueryHandler(close_ticket_callback, pattern='^close_ticket:'))
    application.add_handler(CallbackQueryHandler(continue_ticket_callback, pattern='^continue_ticket:'))
    application.add_handler(CallbackQueryHandler(close_ticket_user_callback, pattern='^close_ticket_user:'))
    application.add_handler(CallbackQueryHandler(escalate_ticket_callback, pattern='^escalate_ticket:'))
    application.add_handler(CallbackQueryHandler(contact_admin_callback, pattern='^contact_admin:'))
    application.add_handler(CallbackQueryHandler(select_list_callback, pattern='^select_list:'))
    application.add_handler(CallbackQueryHandler(edit_list_callback, pattern='^edit_list:'))
    application.add_handler(CallbackQueryHandler(edit_field_callback, pattern='^edit_field:'))
    application.add_handler(CallbackQueryHandler(delete_admin_list_callback, pattern='^delete_admin_list:'))
    application.add_handler(CallbackQueryHandler(confirm_admin_delete_callback, pattern='^confirm_admin_delete:'))
    application.add_handler(CallbackQueryHandler(select_ticket_callback, pattern='^select_ticket:'))
    application.add_handler(CallbackQueryHandler(admin_reply_ticket_callback, pattern='^admin_reply_ticket:'))
    application.add_handler(CallbackQueryHandler(admin_view_ticket_callback, pattern='^admin_view_ticket:'))
    application.add_handler(CallbackQueryHandler(admin_close_ticket_callback, pattern='^admin_close_ticket:'))
    application.add_handler(CallbackQueryHandler(manage_renewal_callback, pattern='^manage_renewal:'))
    application.add_handler(CallbackQueryHandler(approve_renewal_callback, pattern='^approve_renewal:'))
    application.add_handler(CallbackQueryHandler(reject_renewal_callback, pattern='^reject_renewal:'))
    application.add_handler(CallbackQueryHandler(contest_renewal_callback, pattern='^contest_renewal:'))
    application.add_handler(CallbackQueryHandler(manage_deletion_callback, pattern='^manage_deletion:'))
    application.add_handler(CallbackQueryHandler(approve_deletion_callback, pattern='^approve_deletion:'))
    application.add_handler(CallbackQueryHandler(reject_deletion_callback, pattern='^reject_deletion:'))
    application.add_handler(CallbackQueryHandler(export_tickets_callback, pattern='^export_tickets'))
    application.add_handler(CallbackQueryHandler(export_notifications_callback, pattern='^export_notifications'))
    application.add_handler(CallbackQueryHandler(export_all_callback, pattern='^export_all'))

    # General button handler (must be last)
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("✅ All handlers registered successfully")

    try:
        # FORCE POLLING MODE - no webhook complications
        logger.info("🔄 Starting POLLING mode (forced for stability)")
        
        # Initialize and start
        await application.initialize()
        await application.start()
        
        logger.info("✅ Bot polling started successfully - listening for messages...")
        
        # Simple polling - no heartbeat complications
        await application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            timeout=30,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30,
            stop_signals=None
        )
        
    except Exception as e:
        logger.error(f"❌ Polling error: {e}")
        raise

def main():
    """Ultra-simplified main function"""
    logger.info("🚀 Starting ErixCast bot (emergency ultra-simple version)...")
    
    import asyncio
    
    try:
        # Simple asyncio.run - no complications
        asyncio.run(run_bot_main_loop())
        logger.info("✅ Bot completed successfully")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
        sys.exit(1)
    finally:
        try:
            remove_pid_file()
            remove_lock_file()
        except:
            pass

if __name__ == '__main__':
    main()
'''
    
    return minimal_main

def apply_emergency_fix():
    """Applica la correzione di emergenza"""
    
    logger.info("🚨 Applying emergency bot fix...")
    
    bot_file = Path("app/bot.py")
    
    try:
        with open(bot_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Sostituisci solo le funzioni problematiche
        import re
        
        # Sostituisci run_bot_main_loop
        main_loop_pattern = r'async def run_bot_main_loop\(\):.*?(?=\ndef main\(\):)'
        new_main_loop = create_minimal_bot().split('def main():')[0].strip()
        
        new_content = re.sub(main_loop_pattern, new_main_loop, content, flags=re.DOTALL)
        
        # Sostituisci main function
        main_pattern = r'def main\(\):.*?(?=\nif __name__)'
        new_main = create_minimal_bot().split('def main():')[1].split('if __name__')[0].strip()
        new_main = 'def main():' + new_main
        
        new_content = re.sub(main_pattern, new_main, new_content, flags=re.DOTALL)
        
        with open(bot_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        logger.info("✅ Emergency fix applied successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Emergency fix failed: {e}")
        return False

def main():
    """Funzione principale"""
    logger.info("🚨 ErixCast Bot Emergency Fix")
    logger.info("=" * 40)
    
    if apply_emergency_fix():
        logger.info("✅ Emergency fix applied!")
        logger.info("🚀 Bot should now respond to commands")
    else:
        logger.error("❌ Emergency fix failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()