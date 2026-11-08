FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 UV_LINK_MODE=copy
WORKDIR /app
# Install exactly the locked runtime set. uv is mounted for this build step only.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.13.5,source=/uv,target=/bin/uv \
    uv sync --locked --no-dev
ENV PATH="/opt/venv/bin:$PATH"
COPY core/ ./
COPY deploy/firewall_policy.py /opt/brz/firewall_policy.py
COPY sandbox/browser/seccomp_profile.json /app/brz/seccomp_profile.json
RUN groupadd --gid 10001 brz && useradd --uid 10001 --gid 10001 --create-home brz
USER 10001:10001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
