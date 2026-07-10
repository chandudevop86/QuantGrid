FROM node:20-slim AS build

WORKDIR /app/apps/frontend

ARG VITE_API_URL=/api
ARG VITE_API_BASE_URL=/api
ARG VITE_WS_URL=/ws
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_URL=${VITE_WS_URL}

COPY apps/frontend/package*.json ./
RUN npm ci

COPY apps/frontend ./

RUN npm run build

FROM nginx:1.27-alpine

COPY docker/frontend-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
