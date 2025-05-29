FROM python:3.12-slim

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 8081

CMD ["python", "api.py"]
