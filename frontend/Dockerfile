FROM node:20-alpine AS builder
WORKDIR /web
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=builder /web/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i 's#application/javascript js;#application/javascript js mjs;#' /etc/nginx/mime.types

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
