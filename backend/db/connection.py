from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from config import settings

engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def execute_query(query: str, params: dict = None):
    """Execute a raw SQL query and return results."""
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        conn.commit()
        return result


def fetch_all(query: str, params: dict = None):
    """Execute a query and return all rows as dicts."""
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]


def fetch_one(query: str, params: dict = None):
    """Execute a query and return one row as dict."""
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        row = result.fetchone()
        if row:
            columns = result.keys()
            return dict(zip(columns, row))
        return None
