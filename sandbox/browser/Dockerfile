# Keep this version identical to the installed Python package.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp/home
RUN pip install --no-cache-dir playwright==1.64.1 \
    && groupadd --gid 10001 sandbox \
    && useradd --uid 10001 --gid 10001 --create-home sandbox
COPY runner.py /opt/brz/browser.py
USER 10001:10001
WORKDIR /tmp
CMD ["python", "-u", "-c", "import time; time.sleep(300)"]
