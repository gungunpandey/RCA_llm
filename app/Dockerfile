FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# /app/data  → SQLite DB (plant_dashboard_v2.db) — mounted from /opt/rca_data/db on EC2
# /app/static/uploads → user-uploaded PDFs — mounted from /opt/rca_data/uploads on EC2
# Volume declarations are handled entirely by docker-compose.yml bind mounts.
# Do NOT declare VOLUME here — it would create anonymous Docker volumes that
# shadow the bind mounts defined in docker-compose.yml.

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
