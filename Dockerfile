FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    g++ \
    git \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    libglew-dev \
    libglm-dev \
    libx11-dev \
    libxrandr-dev \
    libxinerama-dev \
    libxcursor-dev \
    libxi-dev \
    libxxf86vm-dev \
    xvfb \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY CMakeLists.txt /app/
COPY src/ /app/src/
COPY deps/ /app/deps/
COPY Cube.stl /app/
COPY Sphere.stl /app/

RUN mkdir -p /app/build && cd /app/build \
    && cmake .. -DCMAKE_BUILD_TYPE=Release \
    && make -j$(nproc)

COPY app.py /app/
COPY mask_to_coco.py /app/
COPY requirements.txt /app/
COPY entrypoint.sh /app/

RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir -r /app/requirements.txt

RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV DISPLAY=:99
ENV XDG_RUNTIME_DIR=/tmp/runtime-appuser
RUN mkdir -p /tmp/runtime-appuser && chmod 700 /tmp/runtime-appuser

EXPOSE 7860

HEALTHCHECK CMD curl -f http://localhost:7860/_stcore/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
