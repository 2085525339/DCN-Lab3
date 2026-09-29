FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY server.py .

EXPOSE 53533/udp
CMD ["python", "server.py"]

