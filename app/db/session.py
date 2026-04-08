from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import get_settings
from urllib.parse import urlparse
import logging
import sys

logger = logging.getLogger(__name__)
settings = get_settings()
db_url = settings.DATABASE_URL

if not db_url:
    logger.error("CRITICAL: DATABASE_URL is missing!")
    sys.exit(1)

# Normalise legacy postgres:// scheme for SQLAlchemy 2.x
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

u = urlparse(db_url)

# Standard Production Configuration
connect_args = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5
}

# If using the public proxy (unlikely goal, but supported), ensure SSL
if "rlwy.net" in db_url and "sslmode" not in db_url:
    # Append sslmode=require for public proxy safety if not present
    sep = "&" if "?" in db_url else "?"
    db_url = f"{db_url}{sep}sslmode=require"

if u.scheme.startswith("sqlite"):
    engine = create_engine(
        db_url,
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        db_url,
        poolclass=NullPool,         # Stateless for Serverless/Containers
        pool_pre_ping=True,         # Detect disconnects before query
        pool_recycle=300,           # Recycle every 5 mins
        connect_args=connect_args
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Scoped session: automatically manages one session per thread.
# Use ScopedSession() to get a session, and ScopedSession.remove() when done.
from sqlalchemy.orm import scoped_session as _scoped_session
ScopedSession = _scoped_session(SessionLocal)
