"""
Database models for the bot application
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Index, Float, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

Base = declarative_base()

# Database session factory - will be initialized in main.py
SessionLocal = None

class List(Base):
    __tablename__ = 'lists'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    cost = Column(String)
    expiry_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # category = Column(String, default='generale')  # generale, premium, speciale - removed for compatibility
    # is_active = Column(Boolean, default=True) - removed for compatibility

    __table_args__ = (
        Index('idx_list_expiry', 'expiry_date'),
        # Index('idx_list_category', 'category'),  # removed for compatibility
    )

class Ticket(Base):
    __tablename__ = 'tickets'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    title = Column(String)
    description = Column(Text)
    status = Column(String, default='open')  # open, escalated, closed, resolved
    # category = Column(String, default='generale')  # generale, tecnico, pagamento, altro - removed for compatibility
    # priority = Column(String, default='media')  # bassa, media, alta, critica - removed for compatibility
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # escalated_at = Column(DateTime) - removed for compatibility
    # resolved_at = Column(DateTime) - removed for compatibility
    # assigned_admin = Column(Integer)  # admin user_id who is handling this ticket - removed for compatibility
    # sla_deadline = Column(DateTime)  # Service Level Agreement deadline - removed for compatibility
    messages = relationship("TicketMessage", back_populates="ticket")

    __table_args__ = (
        Index('idx_ticket_user_status', 'user_id', 'status'),
        Index('idx_ticket_created', 'created_at'),
        Index('idx_ticket_user_created', 'user_id', 'created_at'),  # Nuovo indice per query ottimizzate
        # Index('idx_ticket_category', 'category'),  # removed for compatibility
        # Index('idx_ticket_priority', 'priority'),  # removed for compatibility
        # Index('idx_ticket_sla', 'sla_deadline'),  # removed for compatibility
    )

class TicketMessage(Base):
    __tablename__ = 'ticket_messages'

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey('tickets.id'))
    user_id = Column(BigInteger)
    message = Column(Text)
    is_admin = Column(Boolean, default=False)
    is_ai = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ticket = relationship("Ticket", back_populates="messages")

class UserNotification(Base):
    __tablename__ = 'user_notifications'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    list_name = Column(String)
    days_before = Column(Integer)  # 1, 3, or 5 days before expiry
    # notification_type = Column(String, default='expiry')  # expiry, renewal, custom - removed for compatibility
    # is_active = Column(Boolean, default=True) - removed for compatibility
    # last_sent = Column(DateTime) - removed for compatibility

    __table_args__ = (
        Index('idx_notification_user_list', 'user_id', 'list_name'),
        Index('idx_notification_active', 'user_id', 'days_before'),  # Nuovo indice per query ottimizzate
        # Index('idx_notification_type', 'notification_type'),  # removed for compatibility
    )

class RenewalRequest(Base):
    __tablename__ = 'renewal_requests'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    list_name = Column(String)
    months = Column(Integer)
    cost = Column(String)
    status = Column(String, default='pending')  # pending, approved, rejected, contested
    admin_notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime)
    processed_by = Column(Integer)  # admin user_id who processed it

class TicketFeedback(Base):
    __tablename__ = 'ticket_feedbacks'

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey('tickets.id'))
    user_id = Column(BigInteger, index=True)
    rating = Column(Integer)  # 1-5 stars
    comment = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class UserActivity(Base):
    __tablename__ = 'user_activities'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    action = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    details = Column(Text)
    # session_id = Column(String)  # for tracking user sessions - removed for compatibility

    __table_args__ = (
        Index('idx_activity_user_timestamp', 'user_id', 'timestamp'),  # Nuovo indice per query ottimizzate
    )

class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, index=True)
    action = Column(String)  # create, update, delete, approve, reject, etc.
    target_type = Column(String)  # list, ticket, renewal, user, etc.
    target_id = Column(Integer)
    old_value = Column(Text)
    new_value = Column(Text)
    details = Column(Text)
    ip_address = Column(String)
    user_agent = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class UserBehavior(Base):
    __tablename__ = 'user_behaviors'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    behavior_type = Column(String)  # renewal_pattern, ticket_frequency, response_time, etc.
    data = Column(Text)  # JSON data about the behavior
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class UserProfile(Base):
    __tablename__ = 'user_profiles'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)
    theme = Column(String, default='light')  # light, dark
    language = Column(String, default='it')  # it, en
    timezone = Column(String, default='Europe/Rome')
    notifications_enabled = Column(Boolean, default=True)
    reminder_days = Column(String, default='1,3,5')  # comma-separated days before expiry
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class SystemMetrics(Base):
    __tablename__ = 'system_metrics'

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String)  # memory, cpu, response_time, etc.
    value = Column(Float)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    details = Column(Text)  # JSON with additional context

    __table_args__ = (
        Index('idx_metrics_type_time', 'metric_type', 'timestamp'),
    )

class FeatureFlag(Base):
    __tablename__ = 'feature_flags'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text)
    is_enabled = Column(Boolean, default=False)
    rollout_percentage = Column(Float, default=0.0)  # 0.0 to 1.0
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Alert(Base):
    __tablename__ = 'alerts'

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String)  # memory_high, cpu_high, db_error, uptime_down, etc.
    severity = Column(String, default='warning')  # info, warning, error, critical
    message = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer)  # admin user_id who resolved it

    __table_args__ = (
        Index('idx_alert_type_active', 'alert_type', 'is_active'),
        Index('idx_alert_severity', 'severity'),
    )

class UptimePing(Base):
    __tablename__ = 'uptime_pings'

    id = Column(Integer, primary_key=True, index=True)
    thread_name = Column(String, index=True)  # e.g., 'ping_5min', 'ping_7min', 'ping_10min'
    endpoint = Column(String)  # e.g., '/ping', '/health'
    success = Column(Boolean, default=True)
    response_time_ms = Column(Integer)  # response time in milliseconds
    error_message = Column(Text)  # error details if failed
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_ping_thread_time', 'thread_name', 'timestamp'),
        Index('idx_ping_success_time', 'success', 'timestamp'),
    )

# Create all tables
def create_tables(engine):
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)

# Export all models and utilities for imports
__all__ = [
    'SessionLocal', 'List', 'Ticket', 'TicketMessage', 'UserNotification',
    'RenewalRequest', 'TicketFeedback', 'UserActivity', 'AuditLog',
    'UserBehavior', 'UserProfile', 'SystemMetrics', 'FeatureFlag', 'Alert',
    'UptimePing', 'Base', 'create_tables'
]
