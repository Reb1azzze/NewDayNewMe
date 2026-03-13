# migrations.py
import logging
from pathlib import Path
from database import get_connection

logger = logging.getLogger(__name__)


def run_migrations():
    """Выполняет все миграции БД при старте"""
    conn = get_connection()
    cursor = conn.cursor()

    # Получаем список всех колонок в таблице users
    cursor.execute("PRAGMA table_info(users)")
    columns = {col[1] for col in cursor.fetchall()}

    # 🔥 Миграция 1: добавляем news_category (если нет)
    if "news_category" not in columns:
        logger.info("🔄 Migration: adding news_category column...")
        cursor.execute(
            "ALTER TABLE users ADD COLUMN news_category TEXT DEFAULT 'general'"
        )
        logger.info("✅ Migration complete: news_category added")

    # 🔥 Миграция 2: добавляем digest_sections (если нет)
    if "digest_sections" not in columns:
        logger.info("🔄 Migration: adding digest_sections column...")
        cursor.execute(
            "ALTER TABLE users ADD COLUMN digest_sections TEXT DEFAULT '{\"weather\":true,\"rates\":true,\"crypto\":true,\"news\":true}'"
        )
        logger.info("✅ Migration complete: digest_sections added")

    # 🔥 Миграция 3: добавляем quote_enabled (если нет, для цитаты дня)
    if "quote_enabled" not in columns:
        logger.info("🔄 Migration: adding quote_enabled column...")
        cursor.execute(
            "ALTER TABLE users ADD COLUMN quote_enabled INTEGER DEFAULT 1"
        )
        logger.info("✅ Migration complete: quote_enabled added")

    conn.commit()
    conn.close()
    logger.info("✅ All migrations completed successfully")