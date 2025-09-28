FROM python:3.13-slim


WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY config.py .
COPY bot/ ./bot/
COPY db/ ./db/
ENV PYTHONPATH=/app

CMD ["python", "bot/main.py"]
