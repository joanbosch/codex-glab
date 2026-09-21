FROM node:22-trixie-slim

ARG CODEX_VERSION=0.144.4
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash bubblewrap git glab jq python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g "@openai/codex@${CODEX_VERSION}" \
    && codex --version \
    && npm cache clean --force

COPY app /opt/codex-glab
COPY --chmod=755 entrypoint.sh /usr/local/bin/codex-glab
RUN bash -n /usr/local/bin/codex-glab \
    && python3 /opt/codex-glab/cli.py --list \
    && glab --version
USER node
WORKDIR /home/node
ENTRYPOINT ["codex-glab"]
CMD ["mr-review"]
