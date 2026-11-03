FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
RUN groupadd --gid 10001 sandbox && useradd --uid 10001 --gid 10001 --create-home sandbox
USER 10001:10001
WORKDIR /tmp
CMD ["python", "-u", "-c", "import time; time.sleep(300)"]
