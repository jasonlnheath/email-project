"""Application settings."""

import os
from pathlib import Path
from cryptography.fernet import Fernet


class Settings:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    DB_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'email_app.db'}"
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    CORS_ORIGINS: list[str] = ["*"]
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

    def __post_init__(self):
        self.DATA_DIR.mkdir(exist_ok=True)


settings = Settings()
fernet = Fernet(settings.ENCRYPTION_KEY.encode())
