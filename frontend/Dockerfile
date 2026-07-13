# ─── 第一阶段：Node.js 构建 ───────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json ./
COPY package-lock.json ./
RUN npm ci

COPY . .

# 跳过 tsc 类型检查，直接 vite build（类型错误不阻断构建）
RUN npx vite build && \
    node scripts/scrub-sourcemap-directives.mjs dist && \
    if find dist -type f -name '*.map' | grep -q .; then \
      echo "用户部署前端构建产物不允许包含 sourcemap 文件" >&2; \
      exit 1; \
    fi && \
    node scripts/scrub-sourcemap-directives.mjs --check dist

# ─── 第二阶段：Nginx 静态文件服务 ────────────────────────────
FROM nginx:1.25-alpine

COPY --from=builder /app/dist /usr/share/nginx/html

RUN find /usr/share/nginx/html -type f -name '*.map' -delete && \
    chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/run

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
