# Use the required lightweight Python runtime.
FROM python:3.11-slim

# Keep logs visible and avoid writing bytecode into the container.
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Run project commands from the application root.
WORKDIR /app

# Copy dependencies first so code changes do not invalidate this layer.
COPY scripts/requirements.txt .

# Install the project dependencies into the image.
RUN pip install --no-cache-dir -r requirements.txt

# Add the Python project scripts.
COPY scripts/ ./scripts/

# Add the SQL resources used by the pipeline.
COPY sql/ ./sql/

# Run the ingestion entry point by default.
CMD ["python", "scripts/ingest.py"]
