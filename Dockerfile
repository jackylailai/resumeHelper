FROM python:3.11-slim

# Install Node.js 20 (needed for claude CLI)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install claude CLI. In containers it needs ANTHROPIC_API_KEY or mounted Claude
# credentials; the host interactive login is not available inside the image.
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

# Install Python deps as a separate layer for caching
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .

EXPOSE 8000

# Run DB migrations then start the server
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
