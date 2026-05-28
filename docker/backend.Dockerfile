FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/trading-service

WORKDIR /app

COPY services/trading-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/trading-service /app/services/trading-service

WORKDIR /app/services/trading-service

EXPOSE 8000

CMD ["uvicorn", "Backend.presentation.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
