FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Set execution permission for entrypoint script
RUN chmod +x scripts/entrypoint.sh

# Healthcheck menggunakan modul bawaan Python
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys,os; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + os.getenv('APP_PORT', '8000') + '/health', timeout=5).status==200 else 1)"

# Run entrypoint script
CMD ["/bin/bash", "scripts/entrypoint.sh"]