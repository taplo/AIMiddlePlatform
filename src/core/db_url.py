import os

DEFAULT_DB_URL = "sqlite+aiosqlite:///data/aimp.db"


def get_db_url_from_config() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DB_URL)


def is_mysql(url: str) -> bool:
    return url.startswith("mysql+aiomysql") or url.startswith("mysql://")
