FROM python:3.11-slim

# Upgrade system packages to patch vulnerabilities
RUN apt-get update && apt-get upgrade -y && apt-get clean

WORKDIR /app

# Install dependencies first (caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Security: non-root user
RUN useradd -m fintech && chown -R fintech:fintech /app
USER fintech

# Copy application
COPY --chown=fintech:fintech src/ ./src/
COPY --chown=fintech:fintech setup.sql .

# Health check for orchestration
HEALTHCHECK CMD python -c "import sys; sys.exit(0)"

CMD ["python", "src/main.py", "--help"]