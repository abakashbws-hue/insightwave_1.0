# Stage 1: Build the Angular application
FROM node:latest AS build
WORKDIR /usr/local/app
COPY ./ /usr/local/app/
RUN npm install
#RUN npm run build --prod

# Stage 2: Serve the application with Nginx
#FROM nginx:latest
#COPY --from=build /usr/local/app/dist/insightwave /usr/share/nginx/html
EXPOSE 4200
CMD ["npm", "start"]
