# CRISPR guide capture via kb-python (kite). Pinned by @sha256 in the manifest.
FROM quay.io/biocontainers/kb-python:0.28.2--pyhdfd78af_1
LABEL org.spot.stage="guide"
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
