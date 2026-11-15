# The container IS the sandbox: commands run as an unprivileged user that can only see /workspace.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 rx && mkdir /workspace && chown rx /workspace
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[server]"
USER rx
ENV RX_HOME=/home/rx/.rx RX_SANDBOX=local RX_ALLOW_UNSANDBOXED_AUTO=1
WORKDIR /workspace
EXPOSE 8000
# Publish loopback only:  docker run -p 127.0.0.1:8000:8000 -v "$PWD:/workspace" -e OPENROUTER_API_KEY ...
CMD ["rx", "serve", "--host", "0.0.0.0", "--workspace-root", "/workspace", "--max-mode", "ask"]
