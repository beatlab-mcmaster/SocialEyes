# Base image
FROM ubuntu:24.04
WORKDIR /SocialEyes
ENV DEBIAN_FRONTEND=noninteractive

# System dependencies and Python 3.12
RUN apt update && apt install -y \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-full \
    pipx \
    iputils-ping \  
    libgl1 \
    libglib2.0-0 \
    android-tools-adb \
    && apt clean

# Run demo in venv
CMD ["/bin/bash", "-c", "\
    if [ ! -d \"/SocialEyes/venv\" ]; then \
        python3 -m venv /SocialEyes/venv && \
        source /SocialEyes/venv/bin/activate && \
        pip install --no-cache-dir -r /SocialEyes/requirements.txt; \
    else \
        source /SocialEyes/venv/bin/activate; \
    fi && \
    python /SocialEyes/demo.py"]
