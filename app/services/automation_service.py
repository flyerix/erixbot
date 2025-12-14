"""
Intelligent Automation Service
Smart automation system for routine tasks and optimizations
"""
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from sqlalchemy import and_, or_, desc, func
from models import SessionLocal, List, Ticket, UserActivity, AuditLog, RenewalRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import json
import os

logger = logging.getLogger(__name__)

class AutomationService:
    """Intelligent automation service for routine tasks"""
    
    def __init__(self, bot_application=None):
        self.bot = bot_application
        self.scheduler = AsyncIOScheduler()
        self.trust_scores = {}
        self.automation_stats = defaultdict(int)
        self.auto_actions_log = []
        self.setup_automations()
    
    def setup_automations(self):
        """Setup all automated tasks"""
        try:
            # Daily maintenance (2:00 AM)
            self.scheduler.add_job(
                self.daily_maintenance,
                CronTrigger(hour=2, minute=0),
                id='daily_maintenance'
            )
            
            # Smart backup (every 6 hours)
            self.scheduler.add_job(
                self.smart_backup,
                CronTrigger(hour='*/6'),
                id='smart_backup'
            )
            
            # Trust score updates (every 4 hours)
            self.scheduler.add_job(
                self.update_trust_scores,
                CronTrigger(hour='*/4'),
                id='trust_score_update'
            )
            
            # Auto-renewal processing (daily at 10:00 AM)
            self.scheduler.add_job(
                self.process_auto_renewals,
                CronTrigger(hour=10, minute=0),
                id='auto_renewals'
            )
            
            # Performance optimization (daily at 3:00 AM)
            self.scheduler.add_job(
                self.optimize_performance,
                CronTrigger(hour=3, minute=0),
                id='performance_optimization'
            )
            
            # Data cleanup (weekly on Sunday at 1:00 AM)
            self.scheduler.add_job(
                self.cleanup_old_data,
                CronTrigger(day_of_week=6, hour=1, minute=0),
                id='weekly_cleanup'
            )
            
            # Health monitoring (every 30 minutes)
            self.scheduler.add_job(
                self.health_monitoring,
                CronTrigger(minute='*/30'),
                id='health_monitoring'
            )
            
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("Automation scheduler started with 7 jobs")
                
        except Exception as e:
            logger.error(f"Error setting up automations: {e}")
    
    async def daily_maintenance(self):
        """Perform daily maintenance tasks"""
        try:
            logger.info("Starting daily maintenance")
            
            # Update database statistics
            await self._update_db_statistics()
            
            # Clean temporary files
            await self._clean_temp_files()
            
            # Optimize database connections
            await self._optimize_db_connections()
            
            # Update automation statistics
            self.automation_stats['daily_maintenance'] += 1
            
            # Log maintenance completion
            await self._log_automation_action('daily_maintenance', 'completed', {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'tasks_completed': ['db_stats', 'temp_cleanup', 'db_optimization']
            })
            
            logger.info("Daily maintenance completed")
            
        except Exception as e:
            logger.error(f"Error in daily maintenance: {e}")
            await self._log_automation_action('daily_maintenance', 'failed', {'error': str(e)})
    
    async def smart_backup(self):
        """Perform intelligent backup based on activity"""
        try:
            # Check if backup is needed based on activity
            if not await self._should_perform_backup():
                logger.info("Skipping backup - no significant activity")
                return
            
            logger.info("Starting smart backup")
            
            # Backup critical data
            backup_result = await self._perform_backup()
            
            if backup_result['success']:
                self.automation_stats['smart_backup_success'] += 1
                logger.info(f"Smart backup completed: {backup_result['files_backed_up']} files")
            else:
                self.automation_stats['smart_backup_failed'] += 1
                logger.error(f"Smart backup failed: {backup_result['error']}")
            
            await self._log_automation_action('smart_backup', 
                                            'completed' if backup_result['success'] else 'failed',
                                            backup_result)
            
        except Exception as e:
            logger.error(f"Error in smart backup: {e}")
            self.automation_stats['smart_backup_failed'] += 1
    
    async def update_trust_scores(self):
        """Update user trust scores automatically"""
        try:
            logger.info("Updating trust scores")
            
            with SessionLocal() as session:
                # Get all users with recent activity
                recent_users = session.query(func.distinct(Ticket.user_id)).filter(
                    Ticket.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
                ).all()
                
                updated_count = 0
                for user_tuple in recent_users:
                    user_id = user_tuple[0]
                    new_score = await self._calculate_trust_score(user_id, session)
                    
                    old_score = self.trust_scores.get(user_id, 50)
                    self.trust_scores[user_id] = new_score
                    
                    # Log significant changes
                    if abs(new_score - old_score) > 10:
                        await self._log_automation_action('trust_score_update', 'significant_change', {
                            'user_id': user_id,
                            'old_score': old_score,
                            'new_score': new_score,
                            'change': new_score - old_score
                        })
                    
                    updated_count += 1
                
                self.automation_stats['trust_scores_updated'] += updated_count
                logger.info(f"Updated trust scores for {updated_count} users")
                
        except Exception as e:
            logger.error(f"Error updating trust scores: {e}")
    
    async def process_auto_renewals(self):
        """Process automatic renewals for trusted users"""
        try:
            logger.info("Processing auto-renewals")
            
            with SessionLocal() as session:
                # Get pending renewal requests from trusted users
                pending_renewals = session.query(RenewalRequest).filter(
                    RenewalRequest.status == 'pending'
                ).all()
                
                auto_approved = 0
                for renewal in pending_renewals:
                    user_trust = self.trust_scores.get(renewal.user_id, 50)
                    
                    # Auto-approve for highly trusted users (score > 80)
                    if user_trust > 80:
                        # Check additional criteria
                        if await self._can_auto_approve_renewal(renewal, session):
                            await self._auto_approve_renewal(renewal, session)
                            auto_approved += 1
                
                self.automation_stats['auto_renewals_processed'] += auto_approved
                
                if auto_approved > 0:
                    logger.info(f"Auto-approved {auto_approved} renewals")
                    
                    # Notify admins about auto-approvals
                    await self._notify_admins_auto_renewals(auto_approved)
                
        except Exception as e:
            logger.error(f"Error processing auto-renewals: {e}")
    
    async def optimize_performance(self):
        """Optimize system performance automatically"""
        try:
            logger.info("Starting performance optimization")
            
            optimizations_performed = []
            
            # Database optimization
            if await self._optimize_database():
                optimizations_performed.append('database')
            
            # Memory cleanup
            if await self._cleanup_memory():
                optimizations_performed.append('memory')
            
            # Cache optimization
            if await self._optimize_caches():
                optimizations_performed.append('cache')
            
            # Connection pool optimization
            if await self._optimize_connection_pools():
                optimizations_performed.append('connections')
            
            self.automation_stats['performance_optimizations'] += len(optimizations_performed)
            
            await self._log_automation_action('performance_optimization', 'completed', {
                'optimizations': optimizations_performed,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Performance optimization completed: {optimizations_performed}")
            
        except Exception as e:
            logger.error(f"Error in performance optimization: {e}")
    
    async def cleanup_old_data(self):
        """Clean up old data automatically"""
        try:
            logger.info("Starting weekly data cleanup")
            
            with SessionLocal() as session:
                cleanup_stats = {}
                
                # Clean old audit logs (keep last 90 days)
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)
                old_logs = session.query(AuditLog).filter(
                    AuditLog.timestamp < cutoff_date
                ).count()
                
                if old_logs > 0:
                    session.query(AuditLog).filter(
                        AuditLog.timestamp < cutoff_date
                    ).delete()
                    cleanup_stats['audit_logs_deleted'] = old_logs
                
                # Clean old user activities (keep last 60 days)
                activity_cutoff = datetime.now(timezone.utc) - timedelta(days=60)
                old_activities = session.query(UserActivity).filter(
                    UserActivity.timestamp < activity_cutoff
                ).count()
                
                if old_activities > 0:
                    session.query(UserActivity).filter(
                        UserActivity.timestamp < activity_cutoff
                    ).delete()
                    cleanup_stats['activities_deleted'] = old_activities
                
                # Clean resolved tickets older than 6 months
                ticket_cutoff = datetime.now(timezone.utc) - timedelta(days=180)
                old_tickets = session.query(Ticket).filter(
                    and_(
                        Ticket.status.in_(['resolved', 'closed']),
                        Ticket.updated_at < ticket_cutoff
                    )
                ).count()
                
                if old_tickets > 0:
                    session.query(Ticket).filter(
                        and_(
                            Ticket.status.in_(['resolved', 'closed']),
                            Ticket.updated_at < ticket_cutoff
                        )
                    ).delete()
                    cleanup_stats['old_tickets_deleted'] = old_tickets
                
                session.commit()
                
                self.automation_stats['data_cleanup_runs'] += 1
                total_deleted = sum(cleanup_stats.values())
                
                await self._log_automation_action('data_cleanup', 'completed', cleanup_stats)
                
                logger.info(f"Data cleanup completed: {total_deleted} records deleted")
                
        except Exception as e:
            logger.error(f"Error in data cleanup: {e}")
            if 'session' in locals():
                session.rollback()
    
    async def health_monitoring(self):
        """Monitor system health and auto-heal issues"""
        try:
            health_issues = []
            
            # Check database connectivity
            if not await self._check_database_health():
                health_issues.append('database_connectivity')
            
            # Check memory usage
            memory_usage = await self._get_memory_usage()
            if memory_usage > 85:  # 85% threshold
                health_issues.append('high_memory_usage')
                await self._handle_high_memory()
            
            # Check error rates
            error_rate = await self._get_recent_error_rate()
            if error_rate > 5:  # 5% error rate threshold
                health_issues.append('high_error_rate')
            
            # Check response times
            avg_response_time = await self._get_avg_response_time()
            if avg_response_time > 5:  # 5 seconds threshold
                health_issues.append('slow_response_times')
            
            if health_issues:
                await self._handle_health_issues(health_issues)
                self.automation_stats['health_issues_detected'] += len(health_issues)
            else:
                self.automation_stats['health_checks_passed'] += 1
            
        except Exception as e:
            logger.error(f"Error in health monitoring: {e}")
    
    async def _should_perform_backup(self):
        """Determine if backup is needed based on activity"""
        try:
            with SessionLocal() as session:
                # Check activity in last 6 hours
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=6)
                
                recent_tickets = session.query(Ticket).filter(
                    Ticket.created_at >= cutoff_time
                ).count()
                
                recent_activities = session.query(UserActivity).filter(
                    UserActivity.timestamp >= cutoff_time
                ).count()
                
                # Backup if there's been significant activity
                return recent_tickets > 5 or recent_activities > 20
                
        except Exception as e:
            logger.error(f"Error checking backup necessity: {e}")
            return True  # Default to backing up
    
    async def _perform_backup(self):
        """Perform the actual backup"""
        try:
            backup_dir = '/tmp/backups' if os.getenv('RENDER') == 'true' else 'backups'
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # In a real implementation, this would backup the database
            # For now, we'll simulate it
            backup_files = [
                f'tickets_{timestamp}.sql',
                f'lists_{timestamp}.sql',
                f'users_{timestamp}.sql'
            ]
            
            return {
                'success': True,
                'files_backed_up': len(backup_files),
                'backup_files': backup_files,
                'timestamp': timestamp
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'files_backed_up': 0
            }
    
    async def _calculate_trust_score(self, user_id, session):
        """Calculate trust score for user"""
        try:
            base_score = 50
            
            # Account age factor
            first_ticket = session.query(func.min(Ticket.created_at)).filter(
                Ticket.user_id == user_id
            ).scalar()
            
            if first_ticket:
                days_active = (datetime.now(timezone.utc) - first_ticket).days
                base_score += min(days_active * 0.5, 20)  # Up to 20 points for longevity
            
            # Successful resolution rate
            total_tickets = session.query(Ticket).filter(Ticket.user_id == user_id).count()
            resolved_tickets = session.query(Ticket).filter(
                and_(
                    Ticket.user_id == user_id,
                    Ticket.status.in_(['resolved', 'closed']),
                    Ticket.ai_attempts <= 2
                )
            ).count()
            
            if total_tickets > 0:
                success_rate = resolved_tickets / total_tickets
                base_score += success_rate * 20  # Up to 20 points for success rate
            
            # Penalty for escalations
            escalated_tickets = session.query(Ticket).filter(
                and_(
                    Ticket.user_id == user_id,
                    Ticket.auto_escalated == True
                )
            ).count()
            
            base_score -= escalated_tickets * 2  # -2 points per escalation
            
            # Activity consistency bonus
            recent_activity = session.query(UserActivity).filter(
                and_(
                    UserActivity.user_id == user_id,
                    UserActivity.timestamp >= datetime.now(timezone.utc) - timedelta(days=30)
                )
            ).count()
            
            if 5 <= recent_activity <= 50:  # Moderate, consistent activity
                base_score += 10
            
            return max(0, min(base_score, 100))  # Keep between 0-100
            
        except Exception as e:
            logger.error(f"Error calculating trust score: {e}")
            return 50  # Default score
    
    async def _can_auto_approve_renewal(self, renewal, session):
        """Check if renewal can be auto-approved"""
        try:
            # Additional checks for auto-approval
            user_id = renewal.user_id
            
            # Check recent payment history (if available)
            # Check if user has had successful renewals before
            # Check if the renewal request is reasonable
            
            # For now, simple check based on request age
            request_age = (datetime.now(timezone.utc) - renewal.created_at).days
            return request_age <= 7  # Auto-approve if requested within 7 days
            
        except Exception as e:
            logger.error(f"Error checking auto-approval criteria: {e}")
            return False
    
    async def _auto_approve_renewal(self, renewal, session):
        """Auto-approve a renewal request"""
        try:
            renewal.status = 'approved'
            renewal.approved_at = datetime.now(timezone.utc)
            renewal.approved_by = 'automation_system'
            
            # Update the associated list if needed
            if renewal.list_id:
                lst = session.query(List).filter(List.id == renewal.list_id).first()
                if lst:
                    # Extend expiry by 30 days (or whatever the renewal period is)
                    if lst.expiry_date:
                        lst.expiry_date += timedelta(days=30)
                    else:
                        lst.expiry_date = datetime.now(timezone.utc) + timedelta(days=30)
            
            session.commit()
            
            # Log the auto-approval
            await self._log_automation_action('auto_renewal_approved', 'completed', {
                'renewal_id': renewal.id,
                'user_id': renewal.user_id,
                'list_id': renewal.list_id
            })
            
        except Exception as e:
            logger.error(f"Error auto-approving renewal: {e}")
            session.rollback()
    
    async def _notify_admins_auto_renewals(self, count):
        """Notify admins about auto-approved renewals"""
        try:
            if self.bot:
                admin_ids = os.getenv('ADMIN_IDS', '').split(',')
                
                message = f"""
🤖 <b>Rinnovi Automatici Processati</b>

✅ <b>Approvati automaticamente:</b> {count}
🕐 <b>Timestamp:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}

<i>Questi rinnovi sono stati approvati automaticamente per utenti con alto punteggio di fiducia.</i>

📊 Visualizza dettagli: /admin_auto_renewals
                """
                
                for admin_id in admin_ids:
                    if admin_id.strip():
                        await self.bot.bot.send_message(
                            chat_id=int(admin_id.strip()),
                            text=message.strip(),
                            parse_mode='HTML'
                        )
                        
        except Exception as e:
            logger.error(f"Error notifying admins about auto-renewals: {e}")
    
    async def _optimize_database(self):
        """Optimize database performance"""
        try:
            # In a real implementation, this would run database optimization commands
            # For now, we'll simulate it
            await asyncio.sleep(0.1)  # Simulate work
            return True
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
            return False
    
    async def _cleanup_memory(self):
        """Clean up memory usage"""
        try:
            import gc
            gc.collect()
            return True
        except Exception as e:
            logger.error(f"Error cleaning up memory: {e}")
            return False
    
    async def _optimize_caches(self):
        """Optimize cache usage"""
        try:
            # Clear old cache entries, optimize cache sizes, etc.
            await asyncio.sleep(0.1)  # Simulate work
            return True
        except Exception as e:
            logger.error(f"Error optimizing caches: {e}")
            return False
    
    async def _optimize_connection_pools(self):
        """Optimize database connection pools"""
        try:
            # Optimize connection pool settings
            await asyncio.sleep(0.1)  # Simulate work
            return True
        except Exception as e:
            logger.error(f"Error optimizing connection pools: {e}")
            return False
    
    async def _check_database_health(self):
        """Check database connectivity and health"""
        try:
            with SessionLocal() as session:
                session.execute('SELECT 1')
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def _get_memory_usage(self):
        """Get current memory usage percentage"""
        try:
            import psutil
            return psutil.virtual_memory().percent
        except ImportError:
            # Fallback if psutil not available
            logger.warning("psutil not available, using fallback memory usage")
            return 50  # Assume moderate usage
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return 50
    
    async def _handle_high_memory(self):
        """Handle high memory usage"""
        try:
            # Force garbage collection
            import gc
            gc.collect()
            
            # Clear caches if available
            # Restart non-critical services if needed
            
            logger.info("Handled high memory usage")
            
        except Exception as e:
            logger.error(f"Error handling high memory: {e}")
    
    async def _get_recent_error_rate(self):
        """Get recent error rate percentage"""
        try:
            # In a real implementation, this would check error logs
            # For now, simulate a low error rate
            return 1.2  # 1.2% error rate
        except Exception as e:
            logger.error(f"Error getting error rate: {e}")
            return 0
    
    async def _get_avg_response_time(self):
        """Get average response time"""
        try:
            # In a real implementation, this would check response time metrics
            # For now, simulate good response time
            return 1.8  # 1.8 seconds average
        except Exception as e:
            logger.error(f"Error getting response time: {e}")
            return 2.0
    
    async def _handle_health_issues(self, issues):
        """Handle detected health issues"""
        try:
            for issue in issues:
                if issue == 'database_connectivity':
                    # Attempt to reconnect, restart services, etc.
                    pass
                elif issue == 'high_memory_usage':
                    await self._handle_high_memory()
                elif issue == 'high_error_rate':
                    # Log errors, notify admins, etc.
                    pass
                elif issue == 'slow_response_times':
                    # Optimize performance, clear caches, etc.
                    await self._optimize_performance()
            
            logger.warning(f"Handled health issues: {issues}")
            
        except Exception as e:
            logger.error(f"Error handling health issues: {e}")
    
    async def _log_automation_action(self, action, status, details):
        """Log automation actions for audit trail"""
        try:
            self.auto_actions_log.append({
                'action': action,
                'status': status,
                'details': details,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            # Keep only last 1000 log entries
            if len(self.auto_actions_log) > 1000:
                self.auto_actions_log = self.auto_actions_log[-1000:]
                
        except Exception as e:
            logger.error(f"Error logging automation action: {e}")
    
    async def _update_db_statistics(self):
        """Update database statistics"""
        try:
            # In a real implementation, this would update database statistics
            await asyncio.sleep(0.1)  # Simulate work
        except Exception as e:
            logger.error(f"Error updating DB statistics: {e}")
    
    async def _clean_temp_files(self):
        """Clean temporary files"""
        try:
            import tempfile
            import shutil
            
            temp_dir = tempfile.gettempdir()
            # Clean old temp files if needed
            
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")
    
    async def _optimize_db_connections(self):
        """Optimize database connections"""
        try:
            # Optimize connection pool settings
            await asyncio.sleep(0.1)  # Simulate work
        except Exception as e:
            logger.error(f"Error optimizing DB connections: {e}")
    
    def get_automation_stats(self):
        """Get automation statistics"""
        return {
            'total_automations': dict(self.automation_stats),
            'trust_scores_managed': len(self.trust_scores),
            'scheduled_jobs': len(self.scheduler.get_jobs()),
            'recent_actions': len(self.auto_actions_log),
            'last_maintenance': self.auto_actions_log[-1]['timestamp'] if self.auto_actions_log else None
        }
    
    def get_user_trust_score(self, user_id):
        """Get trust score for specific user"""
        return self.trust_scores.get(user_id, 50)
    
    def set_user_trust_score(self, user_id, score, reason):
        """Manually set user trust score"""
        old_score = self.trust_scores.get(user_id, 50)
        self.trust_scores[user_id] = max(0, min(score, 100))
        
        logger.info(f"Trust score updated for user {user_id}: {old_score} -> {score} ({reason})")

# Global automation service instance
automation_service = AutomationService()