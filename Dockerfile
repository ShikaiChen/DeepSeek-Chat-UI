# 使用官方的 Python 3.9-slim 镜像作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 更新包列表
RUN echo "开始更新包列表..." && \
    apt-get update && \
    echo "包列表更新完成。"

# 安装必要的系统依赖
RUN echo "开始安装系统依赖..." && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    poppler-utils \
    tesseract-ocr && \
    echo "系统依赖安装完成。" && \
    # 清理本地缓存
    rm -rf /var/lib/apt/lists/*

# 将当前目录的内容复制到容器的工作目录中
COPY . /app

# 安装 Python 依赖
RUN echo "开始安装 Python 依赖..." && \
    pip install --no-cache-dir -r requirements.txt && \
    echo "Python 依赖安装完成。"

# 暴露 Streamlit 默认端口
EXPOSE 8501

# 设置环境变量
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# 运行应用
CMD ["streamlit", "run", "app.py"]
