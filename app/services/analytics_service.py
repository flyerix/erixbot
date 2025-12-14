"""
Advanced Analytics Service for ErixCast Bot
Provides comprehensive analytics and reporting capabilities
"""
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from sqlalchemy import func, and_, or_
from models import SessionLocal, Ticket, List, UserActivity, TicketMessage
import logging

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Advanced analytics service for bot performance and usage tracking"""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes cache
        
    def get_dashboard_data(self):
        """Get comprehensive dashboard data"""
        try:
            with SessionLocal() as session:
                now = datetime.now(timezone.utc)
                
                # Basic stats
                total_users = self._get_total_users(session)
                active_tickets = self._get_active_tickets(session)
                total_lists = self._get_total_lists(session)
                
                # Time-based analytics
                daily_stats = self._get_daily_stats(session, now)
                weekly_stats = self._get_weekly_stats(session, now)
                monthly_stats = self._get_monthly_stats(session, now)
                
                # AI Performance
                ai_stats = self._get_ai_performance(session, now)
                
                # System health
                system_health = self._get_system_health(session, now)
                
                return {
                    'overview': {
                        'total_users': total_users,
                        'active_tickets': active_tickets,
                        'total_lists': total_lists,
                        'uptime_percentage': system_health.get('uptime', 99.9)
                    },
                    'daily': daily_stats,
                    'weekly': weekly_stats,
                    'monthly': monthly_stats,
                    'ai_performance': ai_stats,
                    'system_health': system_health,
                    'generated_at': now.isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error generating dashboard data: {e}")
            return self._get_fallback_data()
    
    def _get_total_users(self, session):
        """Get total unique users"""
        return session.query(func.count(func.distinct(Ticket.user_id))).scalar() or 0
    
    def _get_active_tickets(self, session):
        """Get currently active tickets"""
        return session.query(Ticket).filter(
            Ticket.status.in_(['open', 'escalated'])
        ).count()
    
    def _get_total_lists(self, session):
        """Get total lists count"""
        return session.query(List).count()
    
    def _get_daily_stats(self, session, now):
        """Get daily statistics for the last 7 days"""
        stats = []
        for i in range(7):
            date = now - timedelta(days=i)
            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            tickets_created = session.query(Ticket).filter(
                and_(Ticket.created_at >= day_start, Ticket.created_at < day_end)
            ).count()
            
            tickets_resolved = session.query(Ticket).filter(
                and_(
                    Ticket.updated_at >= day_start,
                    Ticket.updated_at < day_end,
                    Ticket.status.in_(['closed', 'resolved'])
                )
            ).count()
            
            stats.append({
                'date': date.strftime('%Y-%m-%d'),
                'tickets_created': tickets_created,
                'tickets_resolved': tickets_resolved,
                'day_name': date.strftime('%A')
            })
        
        return list(reversed(stats))
    
    def _get_weekly_stats(self, session, now):
        """Get weekly statistics for the last 4 weeks"""
        stats = []
        for i in range(4):
            week_start = now - timedelta(weeks=i+1)
            week_end = week_start + timedelta(weeks=1)
            
            tickets = session.query(Ticket).filter(
                and_(Ticket.created_at >= week_start, Ticket.created_at < week_end)
            ).count()
            
            stats.append({
                'week': f"Week {i+1}",
                'tickets': tickets,
                'start_date': week_start.strftime('%Y-%m-%d')
            })
        
        return list(reversed(stats))
    
    def _get_monthly_stats(self, session, now):
        """Get monthly statistics for the last 6 months"""
        stats = []
        for i in range(6):
            month_start = (now.replace(day=1) - timedelta(days=32*i)).replace(day=1)
            month_end = (month_start + timedelta(days=32)).replace(day=1)
            
            tickets = session.query(Ticket).filter(
                and_(Ticket.created_at >= month_start, Ticket.created_at < month_end)
            ).count()
            
            stats.append({
                'month': month_start.strftime('%B %Y'),
                'tickets': tickets,
                'month_code': month_start.strftime('%Y-%m')
            })
        
        return list(reversed(stats))
    
    def _get_ai_performance(self, session, now):
        """Get AI performance metrics"""
        last_week = now - timedelta(days=7)
        
        # Total AI attempts
        total_attempts = session.query(func.sum(Ticket.ai_attempts)).scalar() or 0
        
        # Auto-escalated tickets
        auto_escalated = session.query(Ticket).filter(
            and_(
                Ticket.auto_escalated == True,
                Ticket.created_at >= last_week
            )
        ).count()
        
        # Success rate calculation
        total_tickets_last_week = session.query(Ticket).filter(
            Ticket.created_at >= last_week
        ).count()
        
        success_rate = 0
        if total_tickets_last_week > 0:
            success_rate = ((total_tickets_last_week - auto_escalated) / total_tickets_last_week) * 100
        
        # Average response time (simulated - would need actual timing data)
        avg_response_time = 2.3  # seconds (placeholder)
        
        return {
            'total_attempts': total_attempts,
            'auto_escalated_week': auto_escalated,
            'success_rate': round(success_rate, 1),
            'avg_response_time': avg_response_time,
            'efficiency_score': min(100, round(success_rate + (10 - avg_response_time) * 5, 1))
        }
    
    def _get_system_health(self, session, now):
        """Get system health metrics"""
        # Simulated health metrics (in production, these would come from actual monitoring)
        return {
            'uptime': 99.7,
            'memory_usage': 67.3,
            'cpu_usage': 23.1,
            'database_connections': 8,
            'response_time_avg': 1.2,
            'error_rate': 0.3,
            'last_backup': (now - timedelta(hours=6)).isoformat(),
            'status': 'healthy'
        }
    
    def _get_fallback_data(self):
        """Fallback data in case of errors"""
        return {
            'overview': {
                'total_users': 0,
                'active_tickets': 0,
                'total_lists': 0,
                'uptime_percentage': 99.0
            },
            'error': 'Unable to generate analytics data',
            'generated_at': datetime.now(timezone.utc).isoformat()
        }
    
    def export_data_csv(self, data_type='all'):
        """Export analytics data to CSV format"""
        try:
            dashboard_data = self.get_dashboard_data()
            
            if data_type == 'daily':
                return self._format_csv(dashboard_data['daily'])
            elif data_type == 'weekly':
                return self._format_csv(dashboard_data['weekly'])
            elif data_type == 'monthly':
                return self._format_csv(dashboard_data['monthly'])
            else:
                return json.dumps(dashboard_data, indent=2)
                
        except Exception as e:
            logger.error(f"Error exporting data: {e}")
            return "Error exporting data"
    
    def _format_csv(self, data):
        """Format data as CSV string"""
        if not data:
            return "No data available"
        
        # Get headers from first item
        headers = list(data[0].keys())
        csv_lines = [','.join(headers)]
        
        # Add data rows
        for item in data:
            row = [str(item.get(header, '')) for header in headers]
            csv_lines.append(','.join(row))
        
        return '\n'.join(csv_lines)

# Global analytics service instance
analytics_service = AnalyticsService()