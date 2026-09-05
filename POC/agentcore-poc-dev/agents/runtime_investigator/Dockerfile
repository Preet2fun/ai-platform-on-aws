# v1: plain FastAPI, SQLDatabaseToolkit
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "investigator_a2a_runtime.py"]
