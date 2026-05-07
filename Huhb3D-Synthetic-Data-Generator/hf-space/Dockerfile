FROM ubuntu:22.04

# 1. 安装 Linux 下渲染和编译所需的所有依赖
# 安装编译工具和库
RUN apt-get update && apt-get install -y \
    cmake \
    build-essential \
    pkg-config \
    libglfw3-dev \
    libglew-dev \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    libosmesa6-dev \
    libbenchmark-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. 只拷贝源码和必要文件 (删掉 COPY deps/ 这一行)
COPY CMakeLists.txt .
COPY src/ ./src/
COPY app.py .
COPY requirements.txt .
# 如果你有这些脚本和模型文件，保留它们
COPY mask_to_coco.py .
COPY Cube.stl .
COPY Sphere.stl .

# 3. 编译 C++ 渲染器
RUN mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc)

# 4. 安装 Python 依赖
RUN pip3 install --no-cache-dir -r requirements.txt

# 5. 启动
CMD ["python3", "app.py"]