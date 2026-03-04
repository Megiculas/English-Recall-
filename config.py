from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    OPENROUTER_API_KEY: str
    ALLOWED_USER_ID: int
    LLM_MODEL: str = "stepfun/step-3.5-flash:free"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow missing .env file since environment variables will be provided by Render
        extra = "ignore"

settings = Settings()
