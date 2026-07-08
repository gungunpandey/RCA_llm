FROM python:3.10-slim

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .

# Install CPU torch
RUN pip install --no-cache-dir \
    torch==2.5.1 \
    torchvision==0.20.1 \
    torchaudio==2.5.1

# Install sentence-transformers without letting it pull in a conflicting
# torch build, then explicitly install its transformers dependency with
# normal resolution so tokenizers/safetensors/huggingface-hub come along too.
RUN pip install --no-cache-dir --no-deps sentence-transformers==3.0.1 \
    && pip install --no-cache-dir transformers==4.46.3

# Install everything else (normal dependency resolution — required for
# fastapi/openai/google-genai/weaviate-client, whose transitive deps are
# not pinned above)
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire backend code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]