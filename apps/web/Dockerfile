FROM node:24-alpine AS dependencies
RUN npm install --global npm@10.8.2 --ignore-scripts --no-audit --no-fund
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

FROM node:24-alpine AS builder
RUN npm install --global npm@10.8.2 --ignore-scripts --no-audit --no-fund
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runner
RUN npm install --global npm@10.8.2 --ignore-scripts --no-audit --no-fund
ENV NODE_ENV=production
WORKDIR /app
COPY --from=builder --chown=node:node /app/package.json ./package.json
COPY --from=builder --chown=node:node /app/package-lock.json ./package-lock.json
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/.next ./.next
USER node
EXPOSE 3000
CMD ["npm", "run", "start"]
