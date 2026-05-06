FROM node:20-alpine

WORKDIR /app

# Install dependencies first so this Docker layer is cached across source-only changes.
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

# Bake source into the image (overlaid by the bind mount in dev compose).
COPY . .

# Entrypoint syncs node_modules with package.json on every start, so adding a
# new dependency on the host is auto-picked up after a container restart.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 3000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
