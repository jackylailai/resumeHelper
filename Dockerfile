FROM python:3.11-slim

# Install Node.js 20 (needed for claude CLI) + WeasyPrint runtime deps + CJK
# fonts. Without fonts-noto-cjk Chinese / Japanese / Korean characters render
# as blank glyphs in the WeasyPrint output (e.g. "momo.com (富邦媒體科技)"
# became "momo.com ( )"). fonts-noto-cjk is one package covering all four CJK
# variants and is ~60MB compressed.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 \
    fonts-noto-cjk fonts-noto-color-emoji \
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

# Drop privileges — any RCE in uvicorn / pypdf / a dep no longer yields root
# inside the container. The bind-mounted storage dir at
# /app/backend/storage relies on host perms allowing UID 1000 to write;
# pre-create + chown so a fresh image works without manual host fixup.
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/backend/storage \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Run DB migrations then start the server
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
