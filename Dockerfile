# ====== Базовый образ ======
FROM python:3.11-slim

# ====== Метаданные (опционально) ======
LABEL maintainer="Reb1azzze"
LABEL description="NewDayNewMe Telegram Bot"

# ====== Рабочая директория внутри контейнера ======
WORKDIR /app

# ====== Копируем только requirements.txt сначала (для кэша слоёв) ======
COPY requirements.txt .

# ====== Устанавливаем зависимости ======
RUN pip install --no-cache-dir -r requirements.txt

# ====== Копируем весь код проекта ======
COPY . .

# ====== Переменная окружения для Python (опционально) ======
ENV PYTHONUNBUFFERED=1

# ====== Порт (для вебхуков, если понадобится) ======
EXPOSE 8080

# ====== Точка входа: запускаем бота ======
CMD ["python", "bot.py"]