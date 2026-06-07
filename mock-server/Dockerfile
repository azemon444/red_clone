FROM node:20-alpine

WORKDIR /app

COPY mock-server/package.json mock-server/package-lock.json ./
RUN npm ci --omit=dev

COPY mock-server/ ./
COPY patched-app/assets/default /app/assets/default

ENV NODE_ENV=production
ENV ASSETS_ROOT=/app/assets/default
ENV DATA_DIR=/data
ENV PORT=9090

EXPOSE 9090

CMD ["node", "src/server.js"]
