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

# Expose port
EXPOSE 8000

# Run entrypoint script
CMD ["sh", "scripts/entrypoint.sh"]