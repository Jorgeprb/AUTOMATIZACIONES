FROM node:22-alpine AS dependencies

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM dependencies AS development

COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM dependencies AS build

ARG VITE_API_BASE_URL
ARG VITE_API_TIMEOUT_MS=20000
ARG VITE_ENABLE_DEV_FALLBACKS=false
ARG VITE_PORTAL_MODE=admin
ARG VITE_ADMIN_PORTAL_URL=https://admin.autogal.es
ARG VITE_CLIENT_PORTAL_URL=https://client.autogal.es
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS
ENV VITE_ENABLE_DEV_FALLBACKS=$VITE_ENABLE_DEV_FALLBACKS
ENV VITE_PORTAL_MODE=$VITE_PORTAL_MODE
ENV VITE_ADMIN_PORTAL_URL=$VITE_ADMIN_PORTAL_URL
ENV VITE_CLIENT_PORTAL_URL=$VITE_CLIENT_PORTAL_URL
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS production

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
