FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Прокси для сборки (сервер ходит в интернет только через Squid 10.84.142.62:3128).
# Заданы дефолты, можно переопределить через --build-arg. В финальный образ НЕ попадают.
ARG HTTP_PROXY=http://10.84.142.62:3128
ARG HTTPS_PROXY=http://10.84.142.62:3128
ARG http_proxy=http://10.84.142.62:3128
ARG https_proxy=http://10.84.142.62:3128

COPY requirements.txt .
RUN http_proxy=$http_proxy https_proxy=$https_proxy \
    HTTP_PROXY=$HTTP_PROXY HTTPS_PROXY=$HTTPS_PROXY \
    pip install --no-cache-dir -r requirements.txt

COPY tcell_5g_bot.py .
COPY coverage_map.jpg .

# Том для PicklePersistence (bot_persistence.pkl)
VOLUME ["/app/data"]

CMD ["python", "tcell_5g_bot.py"]
