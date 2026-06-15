FROM nginx:1.27-alpine

# 显式清空代理（宿主机可能设了 HTTP_PROXY，容器内 127.0.0.1 指向自己会卡）
ENV HTTP_PROXY="" \
    HTTPS_PROXY="" \
    http_proxy="" \
    https_proxy="" \
    ALL_PROXY="" \
    no_proxy="localhost,127.0.0.1"

# 写入主配置
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/nginx.conf

# 健康检查
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget -q -O- http://localhost/healthz || exit 1
