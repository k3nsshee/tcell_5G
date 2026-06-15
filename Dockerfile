FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tcell_5g_bot.py .
COPY coverage_map.jpg .

# Том для PicklePersistence (bot_persistence.pkl)
VOLUME ["/app/data"]

CMD ["python", "tcell_5g_bot.py"]
