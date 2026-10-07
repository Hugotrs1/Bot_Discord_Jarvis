FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY jarvis ./jarvis

RUN useradd --create-home jarvis && mkdir -p /app/data && chown jarvis /app/data
USER jarvis

VOLUME ["/app/data"]
CMD ["python", "-m", "jarvis"]
