FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    ruff \
    mypy \
    bandit

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g typescript eslint

WORKDIR /workspace

# Non-root user for safety
RUN useradd -m -u 1000 agent && chown -R agent:agent /workspace
USER agent
