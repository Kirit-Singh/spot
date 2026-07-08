# Cell QC + guide assignment + mixscape. Build context = pipeline/ so the tested
# spot_pipeline.qc logic is installed:  docker build -f stages/cellqc/Dockerfile .
# CPU wheels via pip (reliable); rapids-singlecell base on tcefold for the GPU path.
FROM python:3.12-slim
RUN pip install --no-cache-dir scanpy anndata scikit-learn numpy scipy pyyaml pydantic
COPY src /opt/pipeline/src
COPY pyproject.toml /opt/pipeline/pyproject.toml
RUN pip install --no-cache-dir /opt/pipeline --no-deps
COPY stages/cellqc/cellqc.py /opt/cellqc.py
LABEL org.spot.stage="cellqc"
ENTRYPOINT ["python", "/opt/cellqc.py"]
