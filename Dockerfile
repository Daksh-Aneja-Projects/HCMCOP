# HCM Autopilot Agent — container image
# Deployable on Alibaba Cloud ECS (or any Docker host).

FROM python:3.11-slim

# Avoid interactive prompts and .pyc clutter; unbuffered logs for docker logs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY . .

# Streamlit default port.
EXPOSE 8501

# Basic container healthcheck against Streamlit's health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
    sys.exit(0) if urllib.request.urlopen('http://localhost:8501/_stcore/health').status==200 else sys.exit(1)"

# Run the app. The API key is provided at runtime via -e / --env-file.
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
