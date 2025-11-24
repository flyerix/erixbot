"""
Alert service for monitoring and notifications
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from models import SessionLocal, Alert, SystemMetrics
import asyncio

logger = logging.getLogger(__name__)

class AlertService:
    def __init__(self):
        self.alert_thresholds = {
            'memory_high': {'threshold': 80.0, 'severity': 'warning'},  # 80% memory usage
            'cpu_high': {'threshold': 90.0, 'severity': 'warning'},     # 90% CPU usage
            'db_error': {'severity': 'critical'},
            'uptime_down': {'severity': 'critical'},
            'usage_spike': {'threshold': 200.0, 'severity': 'warning'}, # 200% normal usage
            'response_time_high': {'threshold': 5000, 'severity': 'warning'}  # 5 seconds
        }
        self.active_alerts = {}

    async def check_memory_alert(self, memory_percent: float) -> bool:
        """Check if memory usage triggers an alert"""
        threshold = self.alert_thresholds['memory_high']['threshold']
        if memory_percent > threshold:
            await self.create_alert(
                alert_type='memory_high',
                severity=self.alert_thresholds['memory_high']['severity'],
                message=f"Memory usage is {memory_percent:.1f}%, above threshold of {threshold}%"
            )
            return True
        return False

    async def check_cpu_alert(self, cpu_percent: float) -> bool:
        """Check if CPU usage triggers an alert"""
        threshold = self.alert_thresholds['cpu_high']['threshold']
        if cpu_percent > threshold:
            await self.create_alert(
                alert_type='cpu_high',
                severity=self.alert_thresholds['cpu_high']['severity'],
                message=f"CPU usage is {cpu_percent:.1f}%, above threshold of {threshold}%"
            )
            return True
        return False

    async def check_database_alert(self, error_message: str) -> bool:
        """Check for database errors"""
        await self.create_alert(
            alert_type='db_error',
            severity=self.alert_thresholds['db_error']['severity'],
            message=f"Database error: {error_message}"
        )
        return True

    async def check_uptime_alert(self, service_down: bool) -> bool:
        """Check for service downtime"""
        if service_down:
            await self.create_alert(
                alert_type='uptime_down',
                severity=self.alert_thresholds['uptime_down']['severity'],
                message="Service is down or unresponsive"
            )
            return True
        return False

    async def check_usage_spike_alert(self, current_usage: float, normal_usage: float) -> bool:
        """Check for unexpected usage spikes"""
        threshold = self.alert_thresholds['usage_spike']['threshold']
        spike_ratio = (current_usage / normal_usage) * 100 if normal_usage > 0 else 0

        if spike_ratio > threshold:
            await self.create_alert(
                alert_type='usage_spike',
                severity=self.alert_thresholds['usage_spike']['severity'],
                message=f"Usage spike detected: {spike_ratio:.1f}% of normal usage ({current_usage} vs {normal_usage})"
            )
            return True
        return False

    async def check_response_time_alert(self, response_time_ms: float) -> bool:
        """Check for high response times"""
        threshold = self.alert_thresholds['response_time_high']['threshold']
        if response_time_ms > threshold:
            await self.create_alert(
                alert_type='response_time_high',
                severity=self.alert_thresholds['response_time_high']['severity'],
                message=f"Response time is {response_time_ms:.0f}ms, above threshold of {threshold}ms"
            )
            return True
        return False

    async def create_alert(self, alert_type: str, severity: str, message: str) -> None:
        """Create a new alert in the database"""
        # Check if similar alert is already active
        alert_key = f"{alert_type}_{severity}"
        if alert_key in self.active_alerts:
            # Update existing alert instead of creating new one
            await self.update_alert(alert_key, message)
            return

        session = SessionLocal()
        try:
            alert = Alert(
                alert_type=alert_type,
                severity=severity,
                message=message,
                is_active=True
            )
            session.add(alert)
            session.commit()

            self.active_alerts[alert_key] = {
                'id': alert.id,
                'created_at': datetime.now(timezone.utc),
                'message': message
            }

            logger.warning(f"ALERT_CREATED - Type: {alert_type}, Severity: {severity}, Message: {message}")

            # Send notification to admins
            await self.notify_admins(alert_type, severity, message)

        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
        finally:
            session.close()

    async def update_alert(self, alert_key: str, new_message: str) -> None:
        """Update existing alert with new information"""
        if alert_key not in self.active_alerts:
            return

        alert_id = self.active_alerts[alert_key]['id']
        session = SessionLocal()
        try:
            alert = session.query(Alert).filter(Alert.id == alert_id).first()
            if alert:
                alert.message = new_message
                session.commit()
                logger.info(f"ALERT_UPDATED - ID: {alert_id}, Message: {new_message}")
        except Exception as e:
            logger.error(f"Failed to update alert: {e}")
        finally:
            session.close()

    async def resolve_alert(self, alert_type: str, severity: str, resolved_by: int = None) -> None:
        """Resolve an active alert"""
        alert_key = f"{alert_type}_{severity}"

        if alert_key not in self.active_alerts:
            return

        alert_id = self.active_alerts[alert_key]['id']
        session = SessionLocal()
        try:
            alert = session.query(Alert).filter(Alert.id == alert_id).first()
            if alert and alert.is_active:
                alert.is_active = False
                alert.resolved_at = datetime.now(timezone.utc)
                alert.resolved_by = resolved_by
                session.commit()

                logger.info(f"ALERT_RESOLVED - ID: {alert_id}, Type: {alert_type}")

                # Remove from active alerts
                del self.active_alerts[alert_key]

        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
        finally:
            session.close()

    async def notify_admins(self, alert_type: str, severity: str, message: str) -> None:
        """Send alert notification to all admins"""
        from bot import ADMIN_IDS

        notification_message = f"""🚨 **Sistema Alert**

**Tipo:** {alert_type.upper()}
**Severità:** {severity.upper()}
**Messaggio:** {message}
**Ora:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

🔍 Controlla il pannello admin per dettagli."""

        for admin_id in ADMIN_IDS:
            try:
                # Import here to avoid circular imports
                from telegram import Bot
                from bot import TELEGRAM_BOT_TOKEN

                bot = Bot(token=TELEGRAM_BOT_TOKEN)
                await bot.send_message(
                    chat_id=admin_id,
                    text=notification_message,
                    parse_mode='Markdown'
                )
                logger.info(f"Alert notification sent to admin {admin_id}")
            except Exception as e:
                logger.error(f"Failed to send alert notification to admin {admin_id}: {e}")

    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        session = SessionLocal()
        try:
            alerts = session.query(Alert).filter(Alert.is_active == True).all()
            return [{
                'id': alert.id,
                'type': alert.alert_type,
                'severity': alert.severity,
                'message': alert.message,
                'created_at': alert.created_at.isoformat()
            } for alert in alerts]
        finally:
            session.close()

    async def cleanup_old_alerts(self, days_old: int = 30) -> int:
        """Clean up old resolved alerts"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        session = SessionLocal()
        try:
            deleted_count = session.query(Alert).filter(
                Alert.is_active == False,
                Alert.created_at < cutoff_date
            ).delete()

            session.commit()
            logger.info(f"CLEANUP_COMPLETED - Deleted {deleted_count} old alerts")
            return deleted_count
        finally:
            session.close()

# Global alert service instance
alert_service = AlertService()
