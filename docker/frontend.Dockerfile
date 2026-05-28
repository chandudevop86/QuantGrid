FROM node:20-slim

WORKDIR /app/apps/frontend

COPY apps/frontend/package*.json ./
RUN npm ci

COPY apps/frontend ./

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
