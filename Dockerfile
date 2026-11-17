FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV MCP_TRANSPORT=streamable-http PORT=8000
EXPOSE 8000
USER nobody
CMD ["nsf-grant-intelligence"]
