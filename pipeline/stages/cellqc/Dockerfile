# Cell QC + guide assignment + mixscape. Build context = pipeline/ so the tested
# spot_pipeline.qc logic is installed:  docker build -f stages/cellqc/Dockerfile .
# CPU (scanpy) base -> CI-testable; swap to rapids-singlecell on tcefold for GPU.
FROM mambaorg/micromamba:1.5.8
RUN micromamba install -y -n base -c conda-forge -c bioconda \
      python=3.12 scanpy scikit-misc scrublet pertpy anndata pip && micromamba clean -a -y
COPY src /opt/pipeline/src
COPY pyproject.toml /opt/pipeline/pyproject.toml
RUN pip install /opt/pipeline --no-deps
COPY stages/cellqc/cellqc.py /opt/cellqc.py
LABEL org.spot.stage="cellqc"
ENTRYPOINT ["python", "/opt/cellqc.py"]
