from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
import os

DATABASE_URL = os.getenv(
    'DATABASE_URL', 'sqlite+aiosqlite:///guessshotbot.db'
)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    lang = Column(String, default='ru')
    score = Column(Integer, default=0)
    streak = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    medals = Column(String, default='')  # Список медалей через запятую
    referrer_id = Column(Integer, nullable=True)  # ID пригласившего
    referrals_count = Column(Integer, default=0)  # Количество приглашённых
    timezone = Column(String, default='Europe/Moscow')  # Часовой пояс


class Answer(Base):
    __tablename__ = 'answers'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    question_id = Column(Integer, nullable=False)
    topic = Column(String, nullable=False)  # 'movie' или 'city'
    is_correct = Column(Boolean, nullable=False)
    date = Column(DateTime, nullable=False)


class QuestionSent(Base):
    __tablename__ = 'questions_sent'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    question_id = Column(Integer, nullable=False)
    topic = Column(String, nullable=False)
    sent_at = Column(DateTime, nullable=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
