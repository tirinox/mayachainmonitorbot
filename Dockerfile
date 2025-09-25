FROM python:3.11-slim as production

# Install git (needed for git+ requirements).
# Add build tools only if you compile native deps (commented out below).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      ca-certificates \
 #   build-essential gcc python3-dev libffi-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*


# Optional but nice defaults
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1


WORKDIR /app
ADD ./app/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir discord.py --no-dependencies

CMD [ "python", "./main.py", "/config/config.yaml" ]