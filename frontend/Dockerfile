# syntax=docker/dockerfile:1
# Multi-stage build for the Vite dev server (React 18 + TS strict).
# node_modules lives in an anonymous volume in docker-compose.yml so the
# bind-mount of ./frontend:/app does not hide the installed dependencies.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS runtime
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
