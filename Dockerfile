# -------- Base: Python + Debian slim --------
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /SocialEyes

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1 \
    libglib2.0-0 \
    adb \
    iputils-ping \
 && rm -rf /var/lib/apt/lists/*

# Create a dedicated venv OUTSIDE the bind mount, and add to PATH
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Pre-install requirements at build time for speed
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Default command: open interactive shell
CMD ["/bin/bash"]
