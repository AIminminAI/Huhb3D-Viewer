FROM python:3.10-slim

WORKDIR /app

COPY index.html .
COPY server.py .

RUN useradd -m -u 1000 user
RUN chown -R user:user /app
USER user

EXPOSE 7860

CMD ["python3", "server.py"]
