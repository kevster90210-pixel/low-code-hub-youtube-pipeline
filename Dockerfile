FROM python:3.11-slim

# Install FFmpeg and system deps
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy app
COPY pipeline.py .

# Create data directory for processed tracking
RUN mkdir -p /data

CMD ["python", "pipeline.py"]
