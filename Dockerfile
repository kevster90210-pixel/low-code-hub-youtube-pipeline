FROM python:3.11-slim

# Install FFmpeg and system deps
RUN apt-get update && apt-get install -y \
    ffmpeg \
        fonts-liberation \
            && rm -rf /var/lib/apt/lists/*

            WORKDIR /app

            # Install Python deps FIRST (including playwright)
            COPY requirements.txt .
            RUN pip install --no-cache-dir -r requirements.txt
            RUN pip install --no-cache-dir playwright==1.50.0

            # NOW install playwright browsers (after pip install)
            RUN python -m playwright install chromium
            RUN python -m playwright install-deps chromium

            # Copy app
            COPY pipeline.py .

            # Create data directory for processed tracking
            RUN mkdir -p /data

            CMD ["python", "pipeline.py"]
