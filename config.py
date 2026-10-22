import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "local-development-key")
    APP_ENV = os.environ.get("APP_ENV", "development")
    DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
