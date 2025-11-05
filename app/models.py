"""
Database models for the bot application
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Index, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone

Base = declarative_base()

class List(Base):
    __tablename__ = 'lists'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    cost = Column(String)
    expiry_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    category = Column(String, default='generale')  # generale, premium, speciale
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index('idx_list_expiry', 'expiry_date'),
        Index('idx_list_category', 'category'),
    )

class Ticket(Base):
    __tablename__ = 'tickets'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String)
    description = Column(Text)
    status = Column(String, default='open')  # open, escalated, closed, resolved
    category = Column(String, default='generale')  # generale, tecnico, pagamento, altro
    priority = Column(String, default='media')  # bassa, media, alta, critica
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    escalated_at = Column(DateTime)
    resolved_at = Column(DateTime)
    assigned_admin = Column(Integer)  # admin user_id who is handling this ticket
    sla_deadline = Column(DateTime)  # Service Level Agreement deadline
    messages = relationship("TicketMessage", back_populates="ticket")

    __table_args__ = (
        Index('idx_ticket_user_status', 'user_id', 'status'),
        Index('idx_ticket_created', 'created_at'),
        Index('idx_ticket_category', 'category'),
        Index('idx_ticket_priority', 'priority'),
        Index('idx_ticket_sla', 'sla_deadline'),
    )

class TicketMessage(Base):
    __tablename__ = 'ticket_messages'

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey('tickets.id'))
    user_id = Column(Integer)
    message = Column(Text)
    is_admin = Column(Boolean, default=False)
    is_ai = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ticket = relationship("Ticket", back_populates="messages")

class UserNotification(Base):
    __tablename__ = 'user_notifications'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    list_name = Column(String)
    days_before = Column(Integer)  # 1, 3, or 5 days before expiry
    notification_type = Column(String, default='expiry')  # expiry, renewal, custom
    is_active = Column(Boolean, default=True)
    last_sent = Column(DateTime)

    __table_args__ = (
        Index('idx_notification_user_list', 'user_id', 'list_name'),
        Index('idx_notification_type', 'notification_type'),
    )

class RenewalRequest(Base):
    __tablename__ = 'renewal_requests'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
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
    user_id = Column(Integer, index=True)
    rating = Column(Integer)  # 1-5 stars
    comment = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class UserActivity(Base):
    __tablename__ = 'user_activities'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    action = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    details = Column(Text)
    session_id = Column(String)  # for tracking user sessions

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
    user_id = Column(Integer, index=True)
    behavior_type = Column(String)  # renewal_pattern, ticket_frequency, response_time, etc.
    data = Column(Text)  # JSON data about the behavior
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class UserProfile(Base):
    __tablename__ = 'user_profiles'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)
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

# Create all tables
def create_tables(engine):
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)

# Export all models and utilities for imports
__all__ = [
    'SessionLocal', 'List', 'Ticket', 'TicketMessage', 'UserNotification',
    'RenewalRequest', 'TicketFeedback', 'UserActivity', 'AuditLog',
    'UserBehavior', 'UserProfile', 'SystemMetrics', 'FeatureFlag', 'Alert',
    'Base', 'create_tables'
]
