# Use official nginx image
FROM python:3.9-slim
# RUN rm -rf /usr/share/nginx/html/*
# COPY frontend-project/public /usr/share/nginx/html/
# COPY frontend-project/nginx.conf /etc/nginx/conf.d/default.conf

# COPY requirements.txt ./
# RUN bash -c "pip install -r requirements.txt"
RUN bash -c "apt-get update"
RUN bash -c "apt-get install vim -y"


# RUN bash -c  "apt install npm"
# RUN bash -c   "apt-get install systemd -y"
# RUN bash -c "apt install nginx -y"
# RUN bash -c "apt-get install npm -y"
# RUN bash -c "npm install"
# RUN bash -c "npm install react-scripts --save"
# RUN bash -c "npm install history"
EXPOSE 80
# CMD ["nginx", "-g", "daemon off;"]