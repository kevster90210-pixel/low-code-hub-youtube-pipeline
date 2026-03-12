FROM python:3.11-slim-bookworm

# Install system dependencies for FFmpeg and Playwright/Chromium
RUN apt-get update && apt-get install -y \
    ffmpeg \
        fonts-liberation \
            libasound2 \
                libatk-bridge2.0-0 \
                    libatk1.0-0 \
                        libcairo2 \
                            libcups2 \
                                libdbus-1-3 \
                                    libdrm2 \
                                        libgbm1 \
                                            libglib2.0-0 \
                                                libgtk-3-0 \
                                                    libnspr4 \
                                                        libnss3 \
                                                            libpango-1.0-0 \
                                                                libx11-6 \
                                                                    libxcb1 \
                                                                        libxcomposite1 \
                                                                            libxdamage1 \
                                                                                libxext6 \
                                                                                    libxfixes3 \
                                                                                        libxkbcommon0 \
                                                                                            libxrandr2 \
                                                                                                xvfb \
                                                                                                    && rm -rf /var/lib/apt/lists/*
                                                                                                    
                                                                                                    WORKDIR /app
                                                                                                    
                                                                                                    # Install Python deps
                                                                                                    COPY requirements.txt .
                                                                                                    RUN pip install --no-cache-dir -r requirements.txt
                                                                                                    RUN pip install --no-cache-dir playwright==1.50.0
                                                                                                    
                                                                                                    # Install playwright browsers (system deps already installed above)
                                                                                                    RUN python -m playwright install chromium
                                                                                                    
                                                                                                    # Copy app
                                                                                                    COPY pipeline.py .
                                                                                                    
                                                                                                    # Create data directory for processed tracking
                                                                                                    RUN mkdir -p /data
                                                                                                    
                                                                                                    CMD ["python", "pipeline.py"]
