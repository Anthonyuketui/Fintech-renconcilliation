FROM python:3.11.9-slim

WORKDIR /app

# Install system dependencies and security updates
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    postgresql-client \
    libpq-dev \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create output directory
RUN mkdir -p /app/Sample_Output

# Create non-root user
RUN useradd -m fintech && chown -R fintech:fintech /app

# Copy application code
COPY --chown=fintech:fintech src/ ./src/
COPY --chown=fintech:fintech tests/ ./tests/
COPY --chown=fintech:fintech setup.sql ./

# Switch to non-root user
USER fintech

# Set Python path
ENV PYTHONPATH=/app/src

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "from src.database_manager import DatabaseManager; dm = DatabaseManager(); exit(0 if dm.health_check() else 1)"

CMD ["python", "src/main.py", "--processors", "stripe", "paypal", "square"]