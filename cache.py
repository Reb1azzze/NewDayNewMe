# cache.py
import time
import logging
from typing import Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Элемент кэша с таймаутом"""
    data: Any
    created_at: float
    ttl: int  # время жизни в секундах

    def is_valid(self) -> bool:
        """Проверяет, не истёк ли срок жизни кэша"""
        return time.time() - self.created_at < self.ttl


class APICache:
    """Простой in-memory кэш для API ответов"""

    def __init__(self, default_ttl: int = 600):
        """
        :param default_ttl: время жизни кэша по умолчанию (сек)
        """
        self._cache: dict[str, CacheEntry] = {}
        self.default_ttl = default_ttl
        logger.info(f"🗄️ APICache initialized (default TTL: {default_ttl}s)")

    def get(self, key: str) -> Optional[Any]:
        """Получает данные из кэша, если они ещё валидны"""
        entry = self._cache.get(key)
        if entry and entry.is_valid():
            logger.debug(f"✅ Cache HIT: {key}")
            return entry.data
        if entry:
            logger.debug(f"⏰ Cache EXPIRED: {key}")
            self.delete(key)
        return None

    def set(self, key: str, data: Any, ttl: Optional[int] = None):
        """Сохраняет данные в кэш"""
        ttl = ttl or self.default_ttl
        self._cache[key] = CacheEntry(
            data=data,
            created_at=time.time(),
            ttl=ttl
        )
        logger.debug(f"💾 Cache SET: {key} (TTL: {ttl}s)")

    def delete(self, key: str):
        """Удаляет запись из кэша"""
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"🗑️ Cache DELETE: {key}")

    def clear(self):
        """Очищает весь кэш"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"🧹 Cache cleared ({count} entries removed)")
        return count

    def get_stats(self) -> dict:
        """Возвращает статистику кэша"""
        now = time.time()
        valid = sum(1 for e in self._cache.values() if e.is_valid())
        expired = len(self._cache) - valid
        return {
            "total": len(self._cache),
            "valid": valid,
            "expired": expired,
            "keys": list(self._cache.keys())
        }


# Глобальный экземпляр кэша
api_cache = APICache(default_ttl=600)  # 10 минут по умолчанию


# Хелперы для конкретных API
def get_weather_cache_key(city: str) -> str:
    return f"weather:{city}"


def get_rates_cache_key() -> str:
    return "rates:cbr"


def get_news_cache_key(query: str = "Россия") -> str:
    return f"news:{query}"