# syntax=docker/dockerfile:1
FROM python:3.11
WORKDIR /app
COPY . .
COPY .env /root/.config/gino.env
RUN python -m pip --no-cache install poetry wheel pip --upgrade
RUN python -m pip --no-cache install . 
RUN gino.--help
CMD ["gino., "run"]
