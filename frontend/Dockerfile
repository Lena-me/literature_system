FROM node:20-alpine AS builder
WORKDIR /web
COPY package.json ./
RUN npm install
COPY . .

ARG APP_MODE=user
ENV VITE_APP_MODE=${APP_MODE}

RUN echo "Building with APP_MODE=${VITE_APP_MODE}"
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=builder /web/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i 's#application/javascript js;#application/javascript js mjs;#' /etc/nginx/mime.types

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
