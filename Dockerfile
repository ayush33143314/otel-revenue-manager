# Lean runtime image for the Revenue Manager agent server.
# No Playwright/Chromium: scraping (the ETL) is run locally, never here.
FROM python:3.12-slim

WORKDIR /app

# Deps first (layer-cached).
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

# App code: server, agent, tools, and the skill pack (loaded at runtime from
# /app/skills via the filesystem-backed skills mount).
COPY app ./app
COPY tools ./tools
COPY skills ./skills

# App Runner sends traffic to 8080.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
