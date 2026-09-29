# Build context: repository root (needs shared/ as well as prediction/).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv
COPY shared /srv/shared
COPY prediction/pyproject.toml /srv/prediction/pyproject.toml
COPY prediction/app /srv/prediction/app
RUN pip install /srv/shared /srv/prediction
WORKDIR /srv/prediction
USER nobody
EXPOSE 8002
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
