# database.py
import sqlite3
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Универсальный путь к БД:
# 1. Если есть переменная окружения DB_PATH (для Docker) — используем её
# 2. Иначе — локальная папка рядом с файлом
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).parent / "bot_database.db"))


def get_connection():
    """Возвращает подключение к БД"""
    # Создаём папку, если её нет (важно для Docker)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализирует базу данных"""
    with get_connection() as conn:
        conn.execute("""
                     CREATE TABLE IF NOT EXISTS users
                     (
                         chat_id
                         INTEGER
                         PRIMARY
                         KEY,
                         city
                         TEXT
                         DEFAULT
                         'Kazan,RU',
                         send_time
                         TEXT
                         DEFAULT
                         '09:00',
                         created_at
                         TIMESTAMP
                         DEFAULT
                         CURRENT_TIMESTAMP,
                         updated_at
                         TIMESTAMP
                         DEFAULT
                         CURRENT_TIMESTAMP
                     )
                     """)
        conn.commit()
    logger.info(f"🗄️ База данных инициализирована: {DB_PATH}")


def get_user(chat_id: int) -> dict | None:
    """Получает настройки пользователя из БД"""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT city, send_time FROM users WHERE chat_id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()

    if row:
        return {"city": row["city"], "send_time": row["send_time"]}
    return None


def save_user(chat_id: int, city: str, send_time: str):
    """Сохраняет или обновляет настройки пользователя"""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO users (chat_id, city, send_time, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (chat_id, city, send_time))
        conn.commit()
    logger.debug(f"💾 Saved user {chat_id}: city={city}, time={send_time}")


def create_user_if_not_exists(chat_id: int, city: str, send_time: str):
    """Создаёт пользователя, если его ещё нет в базе"""
    if get_user(chat_id) is None:
        save_user(chat_id, city, send_time)
        logger.info(f"✨ New user created: {chat_id}")


def get_all_users() -> list[dict]:
    """Возвращает всех пользователей"""
    with get_connection() as conn:
        cursor = conn.execute("SELECT chat_id, city, send_time, created_at FROM users")
        return [dict(row) for row in cursor.fetchall()]


def delete_user(chat_id: int):
    """Удаляет пользователя из БД"""
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
        conn.commit()
    logger.info(f"🗑️ User {chat_id} deleted")


def get_stats() -> dict:
    """Возвращает статистику по пользователям"""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor = conn.execute("""
                              SELECT city, COUNT(*) as count
                              FROM users
                              GROUP BY city
                              ORDER BY count DESC
                                  LIMIT 5
                              """)
        top_cities = [dict(row) for row in cursor.fetchall()]

        cursor = conn.execute("""
                              SELECT send_time, COUNT(*) as count
                              FROM users
                              GROUP BY send_time
                              ORDER BY count DESC
                              """)
        time_distribution = [dict(row) for row in cursor.fetchall()]

        cursor = conn.execute("""
                              SELECT COUNT(*)
                              FROM users
                              WHERE date (created_at) = date ('now')
                              """)
        new_today = cursor.fetchone()[0]

    return {
        "total_users": total_users,
        "top_cities": top_cities,
        "time_distribution": time_distribution,
        "new_today": new_today
    }


def search_users(query: str) -> list[dict]:
    """Поиск пользователей по chat_id или городу"""
    with get_connection() as conn:
        cursor = conn.execute("""
                              SELECT chat_id, city, send_time, created_at
                              FROM users
                              WHERE chat_id LIKE ?
                                 OR city LIKE ?
                              """, (f"%{query}%", f"%{query}%"))
        return [dict(row) for row in cursor.fetchall()]


def update_user_field(chat_id: int, field: str, value: str):
    """Обновляет одно поле пользователя"""
    allowed_fields = ["city", "send_time"]
    if field not in allowed_fields:
        raise ValueError(f"Field {field} not allowed")

    with get_connection() as conn:
        conn.execute(f"""
            UPDATE users 
            SET {field} = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE chat_id = ?
        """, (value, chat_id))
        conn.commit()