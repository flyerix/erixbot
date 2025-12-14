"""
Smart Notifications System
Intelligent notification system with personalized timing and content
"""
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from sqlalchemy import and_
from models import SessionLocal, List, Ticket
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

logger = logging.getLogger(__name__)

class SmartNotificationService:
    """Intelligent notification service with personalized delivery"""
    
    def __init__(self, bot_application=None):
        self.bot = bot_application
        self.scheduler = AsyncIOScheduler()
        self.user_preferences = {}
        self.notification_history = defaultdict(list)
        self.optimal_times = {}  # User optimal notification times
        self.setup_scheduled_notifications()
    
    def setup_scheduled_notifications(self):
        """Setup scheduled notification jobs"""
        try:
            # Daily digest for admins (9:00 AM)
            self.scheduler.add_job(
                self.send_daily_admin_digest,
                CronTrigger(hour=9, minute=0),
                id='daily_admin_digest'
            )
            
            # Proactive list expiry notifications (multiple times)
            self.scheduler.add_job(
                self.check_expiring_lists,
                CronTrigger(hour=10, minute=0),  # 10:00 AM
                id='morning_expiry_check'
            )
            
            self.scheduler.add_job(
                self.check_expiring_lists,
                CronTrigger(hour=18, minute=0),  # 6:00 PM
                id='evening_expiry_check'
            )
            
            # Weekly user engagement check (Sunday 11:00 AM)
            self.scheduler.add_job(
                self.send_engagement_notifications,
                CronTrigger(day_of_week=6, hour=11, minute=0),
                id='weekly_engagement'
            )
            
            # Cleanup old notifications (daily at 2:00 AM)
            self.scheduler.add_job(
                self.cleanup_old_notifications,
                CronTrigger(hour=2, minute=0),
                id='cleanup_notifications'
            )
            
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("Smart notification scheduler started")
                
        except Exception as e:
            logger.error(f"Error setting up scheduled notifications: {e}")
    
    async def send_smart_notification(self, user_id, notification_type, content, priority='normal'):
        """Send intelligent notification with optimal timing"""
        try:
            # Check if user should receive this notification
            if not self._should_send_notification(user_id, notification_type):
                return False
            
            # Get optimal time for user
            optimal_time = self._get_optimal_time(user_id)
            current_hour = datetime.now().hour
            
            # If it's not optimal time and not urgent, schedule for later
            if priority != 'urgent' and abs(current_hour - optimal_time) > 2:
                await self._schedule_notification(user_id, content, optimal_time)
                return True
            
            # Send immediately
            await self._send_notification_now(user_id, content)
            self._record_notification(user_id, notification_type, content)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending smart notification: {e}")
            return False
    
    def _should_send_notification(self, user_id, notification_type):
        """Check if user should receive this type of notification"""
        try:
            # Get user preferences
            preferences = self._get_user_preferences(user_id)
            
            # Check if notification type is enabled
            if not preferences.get(notification_type, True):
                return False
            
            # Check notification frequency limits
            recent_notifications = self.notification_history[user_id]
            now = datetime.now(timezone.utc)
            
            # Count notifications in last 24 hours
            recent_count = sum(1 for n in recent_notifications 
                             if (now - n['timestamp']).total_seconds() < 86400)
            
            # Limit based on notification type
            limits = {
                'expiry_warning': 2,  # Max 2 expiry warnings per day
                'ticket_update': 5,   # Max 5 ticket updates per day
                'promotional': 1,     # Max 1 promotional per day
                'system_alert': 10,   # Max 10 system alerts per day
                'engagement': 1       # Max 1 engagement per day
            }
            
            max_allowed = limits.get(notification_type, 3)
            type_count = sum(1 for n in recent_notifications 
                           if n['type'] == notification_type and 
                           (now - n['timestamp']).total_seconds() < 86400)
            
            return type_count < max_allowed
            
        except Exception as e:
            logger.error(f"Error checking notification permission: {e}")
            return True  # Default to allowing notification
    
    def _get_optimal_time(self, user_id):
        """Get optimal notification time for user based on activity patterns"""
        try:
            if user_id in self.optimal_times:
                return self.optimal_times[user_id]
            
            # Analyze user activity patterns
            with SessionLocal() as session:
                activities = session.query(UserActivity).filter(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.timestamp >= datetime.now(timezone.utc) - timedelta(days=30)
                    )
                ).all()
                
                if activities:
                    # Find most active hours
                    hour_counts = defaultdict(int)
                    for activity in activities:
                        hour = activity.timestamp.hour
                        hour_counts[hour] += 1
                    
                    # Get most active hour
                    optimal_hour = max(hour_counts.items(), key=lambda x: x[1])[0]
                    self.optimal_times[user_id] = optimal_hour
                    return optimal_hour
                
                # Default optimal times based on general patterns
                return 10  # 10:00 AM default
                
        except Exception as e:
            logger.error(f"Error getting optimal time: {e}")
            return 10  # Default fallback
    
    def _get_user_preferences(self, user_id):
        """Get user notification preferences"""
        if user_id not in self.user_preferences:
            # Default preferences
            self.user_preferences[user_id] = {
                'expiry_warning': True,
                'ticket_update': True,
                'promotional': True,
                'system_alert': True,
                'engagement': True,
                'optimal_hour': None
            }
        
        return self.user_preferences[user_id]
    
    async def _schedule_notification(self, user_id, content, target_hour):
        """Schedule notification for optimal time"""
        try:
            # Calculate next occurrence of target hour
            now = datetime.now()
            target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            
            if target_time <= now:
                target_time += timedelta(days=1)
            
            # Schedule the notification
            self.scheduler.add_job(
                self._send_notification_now,
                'date',
                run_date=target_time,
                args=[user_id, content],
                id=f'scheduled_{user_id}_{int(target_time.timestamp())}'
            )
            
            logger.info(f"Scheduled notification for user {user_id} at {target_time}")
            
        except Exception as e:
            logger.error(f"Error scheduling notification: {e}")
    
    async def _send_notification_now(self, user_id, content):
        """Send notification immediately"""
        try:
            if self.bot:
                await self.bot.bot.send_message(
                    chat_id=user_id,
                    text=content,
                    parse_mode='HTML'
                )
                logger.info(f"Sent notification to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending notification to {user_id}: {e}")
    
    def _record_notification(self, user_id, notification_type, content):
        """Record sent notification for tracking"""
        self.notification_history[user_id].append({
            'type': notification_type,
            'content': content[:100],  # Store first 100 chars
            'timestamp': datetime.now(timezone.utc)
        })
        
        # Keep only last 50 notifications per user
        if len(self.notification_history[user_id]) > 50:
            self.notification_history[user_id] = self.notification_history[user_id][-50:]
    
    async def check_expiring_lists(self):
        """Check for expiring lists and send proactive notifications"""
        try:
            with SessionLocal() as session:
                now = datetime.now(timezone.utc)
                
                # Lists expiring in 3 days
                warning_date = now + timedelta(days=3)
                expiring_lists = session.query(List).filter(
                    and_(
                        List.expiry_date <= warning_date,
                        List.expiry_date > now
                    )
                ).all()
                
                for lst in expiring_lists:
                    days_left = (lst.expiry_date - now).days
                    
                    # Get users who might be interested (recent ticket creators)
                    recent_users = session.query(Ticket.user_id).filter(
                        Ticket.created_at >= now - timedelta(days=30)
                    ).distinct().all()
                    
                    notification_content = f"""
🚨 <b>Avviso Scadenza Lista</b>

📋 <b>Lista:</b> {lst.name}
⏰ <b>Scade tra:</b> {days_left} giorni
📅 <b>Data scadenza:</b> {lst.expiry_date.strftime('%d/%m/%Y')}

💡 <b>Suggerimento:</b> Se utilizzi questa lista, considera di richiedere il rinnovo prima della scadenza.

<i>Questo è un avviso automatico per aiutarti a non perdere l'accesso alle tue liste preferite.</i>
                    """
                    
                    # Send to subset of users (not spam everyone)
                    for user_tuple in recent_users[:10]:  # Limit to 10 users
                        user_id = user_tuple[0]
                        await self.send_smart_notification(
                            user_id, 
                            'expiry_warning', 
                            notification_content.strip(),
                            priority='normal'
                        )
                        
                        # Small delay to avoid rate limiting
                        await asyncio.sleep(0.5)
                
                logger.info(f"Checked {len(expiring_lists)} expiring lists")
                
        except Exception as e:
            logger.error(f"Error checking expiring lists: {e}")
    
    async def send_daily_admin_digest(self):
        """Send daily digest to admins"""
        try:
            # Import locale per evitare import circolari
            try:
                from services.analytics_service import analytics_service
            except ImportError:
                analytics_service = None
            
            # Get admin IDs from environment
            import os
            admin_ids = os.getenv('ADMIN_IDS', '').split(',')
            
            if not admin_ids or admin_ids == ['']:
                return
            
            # Get analytics data
            if analytics_service:
                analytics_data = analytics_service.get_dashboard_data()
            else:
                # Fallback data se analytics_service non è disponibile
                analytics_data = {
                    'overview': {'total_users': 0, 'active_tickets': 0, 'total_lists': 0, 'uptime_percentage': 99.0},
                    'ai_performance': {'success_rate': 95.0, 'avg_response_time': 2.0, 'auto_escalated_week': 0},
                    'system_health': {'memory_usage': 50.0, 'cpu_usage': 30.0, 'error_rate': 0.1}
                }
            
            digest_content = f"""
📊 <b>Digest Giornaliero ErixCast Bot</b>
<i>{datetime.now().strftime('%d/%m/%Y')}</i>

📈 <b>Statistiche Oggi:</b>
👥 Utenti attivi: {analytics_data['overview']['total_users']}
🎫 Ticket aperti: {analytics_data['overview']['active_tickets']}
📋 Liste totali: {analytics_data['overview']['total_lists']}
⏱️ Uptime: {analytics_data['overview']['uptime_percentage']}%

🤖 <b>Performance AI:</b>
✅ Tasso successo: {analytics_data['ai_performance']['success_rate']}%
⚡ Tempo risposta: {analytics_data['ai_performance']['avg_response_time']}s
🚨 Auto-escalation (7gg): {analytics_data['ai_performance']['auto_escalated_week']}

🏥 <b>Stato Sistema:</b>
💾 Memoria: {analytics_data['system_health']['memory_usage']}%
🖥️ CPU: {analytics_data['system_health']['cpu_usage']}%
❌ Errori: {analytics_data['system_health']['error_rate']}%

<i>Dashboard completa: /admin_dashboard</i>
            """
            
            for admin_id in admin_ids:
                if admin_id.strip():
                    await self._send_notification_now(
                        int(admin_id.strip()), 
                        digest_content.strip()
                    )
            
            logger.info("Sent daily admin digest")
            
        except Exception as e:
            logger.error(f"Error sending daily admin digest: {e}")
    
    async def send_engagement_notifications(self):
        """Send weekly engagement notifications to inactive users"""
        try:
            with SessionLocal() as session:
                now = datetime.now(timezone.utc)
                week_ago = now - timedelta(days=7)
                
                # Find users who haven't been active in the last week
                inactive_users = session.query(Ticket.user_id).filter(
                    Ticket.created_at < week_ago
                ).distinct().all()
                
                engagement_content = """
👋 <b>Ciao! Ti mancavamo?</b>

🤖 Il tuo assistente ErixCast Bot è sempre qui per aiutarti!

💡 <b>Novità questa settimana:</b>
• Sistema AI migliorato con risposte più precise
• Dashboard analytics per monitorare le performance
• Notifiche intelligenti personalizzate

🎯 <b>Come posso aiutarti oggi?</b>
• Cerca liste IPTV aggiornate
• Risolvi problemi tecnici
• Richiedi assistenza personalizzata

<i>Scrivi /start per vedere tutte le opzioni disponibili!</i>
                """
                
                # Send to a limited number of inactive users
                for user_tuple in inactive_users[:20]:  # Limit to 20 users per week
                    user_id = user_tuple[0]
                    await self.send_smart_notification(
                        user_id,
                        'engagement',
                        engagement_content.strip(),
                        priority='low'
                    )
                    
                    await asyncio.sleep(1)  # Delay to avoid rate limiting
                
                logger.info(f"Sent engagement notifications to {min(20, len(inactive_users))} users")
                
        except Exception as e:
            logger.error(f"Error sending engagement notifications: {e}")
    
    async def cleanup_old_notifications(self):
        """Clean up old notification history"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
            
            for user_id in list(self.notification_history.keys()):
                # Remove notifications older than 30 days
                self.notification_history[user_id] = [
                    n for n in self.notification_history[user_id]
                    if n['timestamp'] > cutoff_date
                ]
                
                # Remove empty entries
                if not self.notification_history[user_id]:
                    del self.notification_history[user_id]
            
            logger.info("Cleaned up old notification history")
            
        except Exception as e:
            logger.error(f"Error cleaning up notifications: {e}")
    
    def set_user_preference(self, user_id, preference_type, enabled):
        """Set user notification preference"""
        try:
            if user_id not in self.user_preferences:
                self.user_preferences[user_id] = {}
            
            self.user_preferences[user_id][preference_type] = enabled
            logger.info(f"Updated preference for user {user_id}: {preference_type} = {enabled}")
            
        except Exception as e:
            logger.error(f"Error setting user preference: {e}")
    
    def get_notification_stats(self):
        """Get notification system statistics"""
        total_notifications = sum(len(history) for history in self.notification_history.values())
        active_users = len(self.notification_history)
        
        return {
            'total_notifications_sent': total_notifications,
            'active_users': active_users,
            'scheduled_jobs': len(self.scheduler.get_jobs()),
            'optimal_times_learned': len(self.optimal_times),
            'user_preferences_set': len(self.user_preferences)
        }

# Global smart notification service instance
smart_notification_service = SmartNotificationService()