FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY core/requirements.txt core/constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY core/ ./
COPY deploy/firewall_policy.py /opt/brz/firewall_policy.py
COPY sandbox/browser/seccomp_profile.json /app/brz/seccomp_profile.json
RUN groupadd --gid 10001 brz && useradd --uid 10001 --gid 10001 --create-home brz
USER 10001:10001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
