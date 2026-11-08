FROM node:24-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
RUN addgroup -S -g 10001 dashboard && adduser -S -u 10001 -G dashboard dashboard
COPY --from=builder --chown=dashboard:dashboard /app/.next/standalone ./
COPY --from=builder --chown=dashboard:dashboard /app/.next/static ./.next/static
USER dashboard
EXPOSE 3000
CMD ["node", "server.js"]
