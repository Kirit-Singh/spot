# Pseudobulk differential expression (DESeq2), target vs NTC. Pinned by manifest.
FROM bioconductor/bioconductor_docker:RELEASE_3_19
RUN R -e "BiocManager::install(c('DESeq2','edgeR'), update=FALSE, ask=FALSE)"
LABEL org.spot.stage="de"
COPY de.R /opt/de.R
ENTRYPOINT ["Rscript", "/opt/de.R"]
