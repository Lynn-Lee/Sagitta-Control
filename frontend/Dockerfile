# ─── 第一阶段：Node.js 构建 ───────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# 跳过 tsc 类型检查，直接 vite build（类型错误不阻断构建）
RUN npx vite build && \
    if find dist -type f -name '*.map' | grep -q .; then \
      echo "商业前端构建产物不允许包含 sourcemap 文件" >&2; \
      exit 1; \
    fi

# ─── 第二阶段：Nginx 静态文件服务 ────────────────────────────
FROM nginx:1.25-alpine

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
