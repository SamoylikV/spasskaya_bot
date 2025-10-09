FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install redis

COPY bridge/ ./bridge/
COPY config.py .
COPY db/ ./db/

CMD ["python", "bridge/main.py"]
