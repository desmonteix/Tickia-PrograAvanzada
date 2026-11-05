# Build stage
FROM node:22-alpine AS build-stage
WORKDIR /app

# Copy package.json and package-lock.json
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy rest of the code
COPY . .

# Build the project
# Pass VITE_API_URL argument if needed during build time
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_CULQI_PUBLIC_KEY
ENV VITE_CULQI_PUBLIC_KEY=$VITE_CULQI_PUBLIC_KEY

RUN npm run build

# Production stage
FROM nginx:alpine AS production-stage

# Render the backend origin at container startup using nginx's envsubst entrypoint.
ENV API_UPSTREAM=http://backend:8000
ENV TRUSTED_INGRESS_CIDR=127.0.0.1/32
ENV PROXY_SHARED_SECRET=""
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Copy built assets from build-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
