FROM node:20-alpine

# 显式清空代理（宿主机设置了 HTTP_PROXY，容器内 127.0.0.1 指向自己，必须禁用）
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV http_proxy=""
ENV https_proxy=""
ENV ALL_PROXY=""
ENV no_proxy="localhost,127.0.0.1"

WORKDIR /app

# 复制依赖文件
COPY package*.json ./

# 配置 npm 使用国内镜像源并安装依赖
RUN npm config set registry https://registry.npmmirror.com && \
    npm install

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 5173

# 默认命令
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
