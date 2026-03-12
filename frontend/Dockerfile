FROM node:20-alpine

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
