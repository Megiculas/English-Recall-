from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, DateTime, Integer, Boolean, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    # Telegram User ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    
    # Гейміфікація та статистика
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    max_streak: Mapped[int] = mapped_column(Integer, default=0)

class Word(Base):
    __tablename__ = "words"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    # Основні дані
    word: Mapped[str] = mapped_column(String, index=True)
    context_given: Mapped[str] = mapped_column(Text, nullable=True) # Як користувач ввів слово (напр. фраза)
    
    # Згенероване LLM
    llm_response: Mapped[dict] = mapped_column(JSONB, nullable=True) 
    
    # Інтервальні повторення
    level: Mapped[int] = mapped_column(Integer, default=0) # Рівень від 0 до 6
    next_review: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        index=True
    )
    is_learned: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Прапорець, щоб планувальник не спамив одне й те саме слово, поки юзер не відповість
    is_waiting_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (
        UniqueConstraint('user_id', 'word', name='uq_word_user_word'),
        Index('ix_word_user_word', 'user_id', 'word'),
    )
