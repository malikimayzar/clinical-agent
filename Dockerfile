# 1. Gunakan image yang lebih ringan jika memungkinkan
FROM python:3.12-slim

WORKDIR /app

# 2. System dependencies minimal
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Copy requirements dan install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir uvicorn[standard] gunicorn

# 4. Copy source code
COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]