#!/usr/bin/env Rscript
# spot pipeline DE stage: pseudobulk DESeq2, target vs NTC.
# Emits COMPUTED stats only; targets below min-cells -> "insufficient_power", never a fake p.
# Args: counts.csv coldata.csv outdir min_cells min_abs_log2fc padj gene_min_count
suppressMessages({library(DESeq2)})
a <- commandArgs(trailingOnly = TRUE)
counts <- as.matrix(read.csv(a[1], row.names = 1))
coldata <- read.csv(a[2], row.names = 1)             # columns: target (with 'NTC'), n_cells
outdir <- a[3]; dir.create(outdir, showWarnings = FALSE, recursive = TRUE)
min_cells <- as.integer(a[4]); lfc <- as.numeric(a[5]); padj <- as.numeric(a[6]); gmin <- as.integer(a[7])

keep_genes <- rowSums(counts >= gmin) >= 2
counts <- counts[keep_genes, ]
coldata$target <- relevel(factor(coldata$target), ref = "NTC")

targets <- setdiff(levels(coldata$target), "NTC")
res_all <- list(); underpowered <- character(0)
for (tg in targets) {
  if (sum(coldata$n_cells[coldata$target == tg]) < min_cells) { underpowered <- c(underpowered, tg); next }
  sub <- coldata$target %in% c("NTC", tg)
  dds <- DESeqDataSetFromMatrix(counts[, sub], coldata[sub, , drop = FALSE], ~target)
  dds <- DESeq(dds, quiet = TRUE)
  r <- as.data.frame(results(dds, contrast = c("target", tg, "NTC")))
  r$gene <- rownames(r); r$target <- tg
  res_all[[tg]] <- r[!is.na(r$padj) & r$padj <= padj & abs(r$log2FoldChange) >= lfc, ]
}
de <- do.call(rbind, res_all)
write.csv(de, file.path(outdir, "de_table.csv"), row.names = FALSE)
writeLines(underpowered, file.path(outdir, "insufficient_power.txt"))
cat(sprintf("DE: %d targets tested, %d rows, %d insufficient_power\n",
            length(targets) - length(underpowered), nrow(de), length(underpowered)))
