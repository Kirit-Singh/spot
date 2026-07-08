# STARsolo GEX align+count. Pinned by @sha256 in the manifest.
FROM quay.io/biocontainers/star:2.7.11b--h43eeafb_1
LABEL org.spot.stage="starsolo"
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
