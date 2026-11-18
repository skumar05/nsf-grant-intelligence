FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
# Setting PORT is what makes the server serve HTTP (it is stdio when PORT is unset).
ENV PORT=8080
EXPOSE 8080
USER nobody
# slim has no curl, so probe with the standard library
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=3)"
CMD ["nsf-grant-intelligence"]
