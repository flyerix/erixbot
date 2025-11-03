from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from sqlalchemy.pool import QueuePool
from datetime import datetime, timezone
import os

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Enhanced connection pooling for better performance
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,  # Number of connections to keep open
    max_overflow=20,  # Additional connections allowed
    pool_timeout=30,  # Timeout for getting connection from pool
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=False  # Disable SQL logging in production
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Scoped session for thread safety
ScopedSession = scoped_session(SessionLocal)

Base = declarative_base()

class List(Base):
    __tablename__ = 'lists'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    cost = Column(String)
    expiry_date = Column(DateTime, index=True)  # Added index for expiry queries
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)  # Added index for time-based queries

class Ticket(Base):
    __tablename__ = 'tickets'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String, index=True)  # Added index for title searches
    description = Column(Text)
    status = Column(String, default='open', index=True)  # open, closed, escalated - added index for status filtering
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)
    messages = relationship("TicketMessage", back_populates="ticket")

class TicketMessage(Base):
    __tablename__ = 'ticket_messages'

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey('tickets.id'), index=True)  # Added index for ticket filtering
    user_id = Column(Integer, index=True)
    message = Column(Text)
    is_admin = Column(Boolean, default=False, index=True)  # Added index for admin filtering
    is_ai = Column(Boolean, default=False, index=True)  # Added index for AI filtering
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    ticket = relationship("Ticket", back_populates="messages")

class UserNotification(Base):
    __tablename__ = 'user_notifications'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    list_name = Column(String, index=True)  # Added index for list name queries
    days_before = Column(Integer, index=True)  # 1, 3, or 5 days before expiry - added index

class RenewalRequest(Base):
    __tablename__ = 'renewal_requests'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    list_name = Column(String, index=True)  # Added index for list name queries
    months = Column(Integer)
    cost = Column(String)
    status = Column(String, default='pending', index=True)  # pending, approved, rejected, contested - added index
    admin_notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    processed_at = Column(DateTime, index=True)
    processed_by = Column(Integer, index=True)  # admin user_id who processed it - added index

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
    action = Column(String, index=True)  # Added index for action filtering
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    details = Column(Text)

Base.metadata.create_all(bind=engine)

