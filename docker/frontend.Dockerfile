FROM node:20-slim AS build

WORKDIR /app/apps/frontend

COPY apps/frontend/package*.json ./
RUN npm ci

COPY apps/frontend ./

RUN npm run build

FROM nginx:1.27-alpine

COPY docker/frontend-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
