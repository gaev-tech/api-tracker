# Stage 1: Build
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --registry https://registry.npmjs.org/
COPY . .
RUN npx --registry https://registry.npmjs.org/ ng build auth --configuration production
RUN npx --registry https://registry.npmjs.org/ ng build app --configuration production
RUN npx --registry https://registry.npmjs.org/ ng build docs --configuration production

# Stage 2: Serve
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist/auth/browser /usr/share/nginx/html/auth
COPY --from=build /app/dist/app/browser /usr/share/nginx/html/app
COPY --from=build /app/dist/docs/browser /usr/share/nginx/html/docs
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
