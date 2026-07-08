"""Generate a tiny synthetic Perturb-seq fixture for the end-to-end test.

Mini reference (2 genes), 10x GEX + guide FASTQ (4 cells), and a guide library
(gA->GENE1, gB->GENE2, NTC). Deterministic (fixed seed). Reads derive from the
mini genes so STARsolo/kite actually map them.
"""

from __future__ import annotations

import gzip
import random
from pathlib import Path

BASE = Path(__file__).parent / "fixtures"
BARCODES = ["AAACCCAAGAAACACT", "AAACCCACAAACCTAC", "AAACCCAGTAAACGCG", "AAACGAAAGAAACCCA"]


def _seq(n: int) -> str:
    return "".join(random.choice("ACGT") for _ in range(n))


def _fastq(path: Path, records: list[tuple[str, str]]) -> None:
    with gzip.open(path, "wt") as f:
        for name, seq in records:
            f.write(f"@{name}\n{seq}\n+\n{'I' * len(seq)}\n")


def main() -> None:
    random.seed(7)
    ref, raw, gl = BASE / "reference", BASE / "raw", BASE / "guides"
    for d in (ref, raw, gl):
        d.mkdir(parents=True, exist_ok=True)

    gene1, gene2, spacer = _seq(1200), _seq(1200), _seq(200)
    chrom = gene1 + spacer + gene2
    with (ref / "mini.fa").open("w") as f:
        f.write(">chr_mini\n")
        for i in range(0, len(chrom), 60):
            f.write(chrom[i : i + 60] + "\n")
    coords = {"GENE1": (1, 1200), "GENE2": (1601, 2800)}
    with (ref / "mini.gtf").open("w") as f:
        for gid, (s, e) in coords.items():
            attr = f'gene_id "{gid}"; transcript_id "{gid}T"; gene_name "{gid}";'
            for feat in ("gene", "transcript", "exon"):
                f.write(f"chr_mini\tsyn\t{feat}\t{s}\t{e}\t.\t+\t.\t{attr}\n")
    (ref / "whitelist.txt").write_text("\n".join(BARCODES) + "\n")

    plan = {
        0: [(gene1, 8), (gene2, 1)],
        1: [(gene1, 7), (gene2, 1)],
        2: [(gene1, 1), (gene2, 8)],
        3: [(gene1, 1), (gene2, 7)],
    }
    r1, r2, rid = [], [], 0
    for ci, cb in enumerate(BARCODES):
        for gseq, cnt in plan[ci]:
            for _ in range(cnt):
                start = random.randint(0, len(gseq) - 90)
                r1.append((f"r{rid}", cb + _seq(12)))
                r2.append((f"r{rid}", gseq[start : start + 90]))
                rid += 1
    _fastq(raw / "gex_R1.fastq.gz", r1)
    _fastq(raw / "gex_R2.fastq.gz", r2)

    protos = {"gA": _seq(20), "gB": _seq(20), "NTC": _seq(20)}
    with (gl / "guides.fa").open("w") as f:
        for name, seq in protos.items():
            f.write(f">{name}\n{seq}\n")
    (gl / "t2g.txt").write_text("gA\tGENE1\ngB\tGENE2\nNTC\tNTC\n")
    assign = {0: "gA", 1: "gA", 2: "gB", 3: "NTC"}
    g1, g2, gid = [], [], 0
    for ci, cb in enumerate(BARCODES):
        for _ in range(5):
            g1.append((f"g{gid}", cb + _seq(12)))
            g2.append((f"g{gid}", protos[assign[ci]] + _seq(70)))
            gid += 1
    _fastq(raw / "guide_R1.fastq.gz", g1)
    _fastq(raw / "guide_R2.fastq.gz", g2)


if __name__ == "__main__":
    main()
