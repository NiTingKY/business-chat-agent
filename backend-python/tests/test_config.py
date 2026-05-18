from __future__ import annotations

from app.config import Settings


def test_settings_default_to_mysql_database_url() -> None:
    settings = Settings(_env_file=None)

    assert (
        settings.resolved_database_url
        == "mysql+aiomysql://root:123456@localhost:3306/travelagent?charset=utf8mb4"
    )


def test_settings_database_url_override_wins() -> None:
    settings = Settings(
        _env_file=None,
        database_url="mysql+aiomysql://travel:travel@db:3306/custom?charset=utf8mb4",
    )

    assert (
        settings.resolved_database_url
        == "mysql+aiomysql://travel:travel@db:3306/custom?charset=utf8mb4"
    )


def test_settings_build_redis_url_from_split_fields() -> None:
    settings = Settings(
        _env_file=None,
        redis_host="redis.local",
        redis_port=6380,
        redis_db=2,
    )

    assert settings.resolved_redis_url == "redis://redis.local:6380/2"
