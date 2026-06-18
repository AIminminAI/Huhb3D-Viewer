FROM python:3.10-slim

# cadquery/OCP 需要的系统依赖
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libegl1 \
    libglu1-mesa \
    libxmu6 \
    libxi6 \
    libxpm4 \
    libxft2 \
    libxt6 \
    libx11-6 \
    libxext6 \
    libomp5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先安装 cadquery（最耗时的依赖）
RUN pip install --no-cache-dir cadquery>=2.3 numpy>=1.24

# 再安装轻量依赖
RUN pip install --no-cache-dir fastapi>=0.104.0 uvicorn>=0.24.0 python-multipart>=0.0.6

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
