# Fargate heavy-embed image (ARM64, matches the ECS task RuntimePlatform).
# Handles large documents whose embedding batch exceeds the Lambda timeout.
FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY handlers/ ./handlers/
COPY heavy_embed.py ./

# The task is invoked with the S3 chunks key(s) to process (via env or command args).
ENTRYPOINT ["python", "heavy_embed.py"]
