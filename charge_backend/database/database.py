from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .settings import db_settings
from .models import Base

connect_args = {"check_same_thread": False}
engine = create_async_engine(
    str(db_settings.sqla_db_uri),
    echo=db_settings.verbose_sql,
    connect_args=connect_args,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)


async def get_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except:
            raise
        finally:
            await session.close()
