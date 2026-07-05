# Build from the REPO ROOT so both backend/ and frontend/ are in context:
#   docker build -f backend/Dockerfile -t plagiarism-detector .
# (docker-compose.yml at the repo root already does this for you.)
FROM python:3.12-slim

# git is required by GitPython to actually clone repositories
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY frontend ./frontend

RUN mkdir -p /app/data
ENV PLAGCHECK_DB_PATH=/app/data/jobs.db
ENV FRONTEND_DIR=/app/frontend

EXPOSE 8000
# Single worker: the bundled SQLite job store is file-locked and not safe for
# concurrent writers across multiple worker processes. See README "Scaling
# beyond a single instance" for the Postgres + Celery upgrade path.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
