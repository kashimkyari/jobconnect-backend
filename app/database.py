from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event

from app.config import settings

# Create async engine
engine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=settings.DEBUG,
    future=True
)

# Ensure DB session timezone is always Nigeria time
@event.listens_for(engine.sync_engine, "connect")
def _set_timezone(dbapi_connection, _connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET TIME ZONE 'Africa/Lagos'")
        cursor.close()
    except Exception:
        # Ignore for DBs that don't support timezone setting
        pass

# Create async session factory
async_session = sessionmaker(
    class_=AsyncSession,
    expire_on_commit=False,
    bind=engine
)

from fastapi import Request

# Dependency to get a DB session
async def get_db(request: Request) -> AsyncSession:
    return request.state.db
