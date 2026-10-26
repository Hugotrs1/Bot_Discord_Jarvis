FROM python:3.12-slim

# Logs affichés tout de suite (docker compose logs), et matplotlib écrit son cache dans /tmp
ENV PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Le bot ne tourne pas en root dans le conteneur
RUN useradd --create-home jarvis
USER jarvis

CMD ["python", "bot.py"]
