FROM python:3.12-slim

WORKDIR /app

# Install dependencies sistem
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# ----------------------------------
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir uvicorn[standard] gunicorn
# ----------------------------------

# Copy hanya folder yang dibutuhkan
COPY ./api ./api
COPY ./agents ./agents
COPY ./integrations ./integrations
COPY ./scheduler ./scheduler

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]