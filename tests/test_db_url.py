import os
from unittest.mock import patch
from src.core.db_url import get_db_url_from_config, is_mysql


def test_default_url_is_sqlite():
    url = get_db_url_from_config()
    assert url.startswith("sqlite")


def test_env_var_overrides():
    with patch.dict(os.environ, {"DATABASE_URL": "mysql+aiomysql://u:p@h/db"}):
        url = get_db_url_from_config()
        assert url.startswith("mysql+aiomysql")


def test_is_mysql_true():
    assert is_mysql("mysql+aiomysql://u:p@h/db")
    assert is_mysql("mysql://u:p@h/db")


def test_is_mysql_false():
    assert not is_mysql("sqlite+aiosqlite:///data/aimp.db")
    assert not is_mysql("postgresql://u:p@h/db")
