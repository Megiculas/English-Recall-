from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, DateTime, Integer, Boolean, Text
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

class Word(Base):
    __tablename__ = "words"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    # Основні дані
    word: Mapped[str] = mapped_column(String, index=True)
    context_given: Mapped[str] = mapped_column(Text, nullable=True) # Як користувач ввів слово (напр. фраза)
    
    # Згенероване LLM (зберігаємо у форматі JSON-строки для простоти)
    llm_response: Mapped[str] = mapped_column(Text, nullable=True) 
    
    # Інтервальні повторення
    level: Mapped[int] = mapped_column(Integer, default=0) # Рівень від 0 до 6
    next_review: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        index=True
    )
    is_learned: Mapped[bool] = mapped_column(Boolean, default=False)
    
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
