from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import QueuePool
from datetime import datetime, timezone
import os

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Enhanced connection pooling for Render compatibility
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,  # Render free tier limit
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,  # Recycle connections every hour
    pool_pre_ping=True  # Verify connections before use
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class List(Base):
    __tablename__ = 'lists'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    cost = Column(String)
    expiry_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Ticket(Base):
    __tablename__ = 'tickets'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String)
    description = Column(Text)
    status = Column(String, default='open')  # open, closed, escalated
    category = Column(String, default='generale')  # generale, tecnico, pagamento, altro
    priority = Column(String, default='media')  # bassa, media, alta, critica
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    messages = relationship("TicketMessage", back_populates="ticket")

    __table_args__ = (
        Index('idx_ticket_user_status', 'user_id', 'status'),
        Index('idx_ticket_created', 'created_at'),
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

    __table_args__ = (
        Index('idx_notification_user_list', 'user_id', 'list_name'),
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

Base.metadata.create_all(bind=engine)
