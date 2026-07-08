# spot pipeline stage: fetch  (pinned by @sha256 in the dataset manifest)
FROM debian:bookworm-slim
LABEL org.spot.stage="fetch"
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
