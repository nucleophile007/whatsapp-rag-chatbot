"""
Database connection and session management
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

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

def get_db_session():
    """
    Get database session (for FastAPI dependency injection)
    
    Usage in FastAPI:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db_session)):
            return db.execute(text("SELECT 1")).all()
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
