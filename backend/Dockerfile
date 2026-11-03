FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt backend/constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY deploy/firewall_policy.py /opt/brz/firewall_policy.py
COPY backend/browser_sandbox/seccomp_profile.json /app/brz/seccomp_profile.json
RUN groupadd --gid 10001 brz && useradd --uid 10001 --gid 10001 --create-home brz
USER 10001:10001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
