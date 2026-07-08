# Cell QC + guide assignment + mixscape. CPU (scanpy) so it is CI-testable;
# swap to a rapids-singlecell base on tcefold for the GPU path. Pinned by manifest.
FROM mambaorg/micromamba:1.5.8
RUN micromamba install -y -n base -c conda-forge -c bioconda \
      python=3.12 scanpy scikit-misc scrublet pertpy anndata && micromamba clean -a -y
LABEL org.spot.stage="cellqc"
COPY cellqc.py /opt/cellqc.py
ENTRYPOINT ["python", "/opt/cellqc.py"]
