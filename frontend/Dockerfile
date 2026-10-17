# Production image for the web app + same-origin gateway (deploy/docker-compose.prod.yml).
# Runtime config (BACKEND_URL, DEMO_PASSWORD, DEMO_RESET_EVERY_HOURS) comes from the environment.
FROM node:24-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
# Not `npm ci`: on Linux it rejects this lockfile over @emnapi peers of Tailwind's optional wasm build,
# which npm never writes into the lock. `npm install` still installs the locked versions.
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
