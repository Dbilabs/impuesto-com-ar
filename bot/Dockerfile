FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

COPY bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY bot /app/bot
COPY data /app/data
RUN mkdir -p /app/data/boveda

ENV PYTHONUNBUFFERED=1
ENV PUBLIC_BOT_URL=https://impuesto.com.ar

EXPOSE 8000

CMD ["sh", "-c", "uvicorn bot.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
