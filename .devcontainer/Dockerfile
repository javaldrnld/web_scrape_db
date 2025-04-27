FROM python:3.11-slim
WORKDIR /workspace
RUN apt-get update && apt-get install -y \
    curl \
    git \
    vim \
 && rm -rf /var/lib/apt/lists/*