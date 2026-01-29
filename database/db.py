"""
Database connection and session management
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
from database.models import Base

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://flowbuilder:flowbuilder123@localhost:5432/whatsapp_flows")

# Create engine
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # Disable pooling for simplicity in Docker
    echo=False  # Set to True for SQL debugging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully")


@contextmanager
def get_db() -> Session:
    """
    Get database session with context manager
    
    Usage:
        with get_db() as db:
            user = db.query(User).first()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_db_session():
    """
    Get database session (for FastAPI dependency injection)
    
    Usage in FastAPI:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db_session)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

