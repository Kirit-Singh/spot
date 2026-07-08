"""Dataset manifest — the reproducibility contract for the pipeline lane.

The manifest IS the gate: given only this, anyone can re-fetch and reproduce a
from-raw Perturb-seq ingest byte-for-byte. Analysis cannot start until it
validates. Symmetric with the Hit/Evidence contract; never carries a computed
statistic, only the inputs + pinned tooling that produce one.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

MANIFEST_SCHEMA_VERSION = "0.1.0"
_SHA256 = "@sha256:"
# Permissive / public licenses spot is allowed to ingest.
ALLOWED_LICENSES = frozenset({"MIT", "CC0", "CC0-1.0", "CC-BY-4.0", "public-domain"})


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LibraryType(StrEnum):
    GEX = "gex"  # gene expression (cDNA)
    GUIDE = "guide"  # CRISPR guide capture


class Chemistry(StrEnum):
    TENX_V2 = "10x_v2"
    TENX_V3 = "10x_v3"


class MOIDesign(StrEnum):
    LOW = "low"  # ~1 guide/cell
    HIGH = "high"


class Aligner(StrEnum):
    STARSOLO = "starsolo"
    KB_PYTHON = "kb_python"


class RunAccession(_M):
    accession: str  # SRR / ERR
    sample: str
    library_type: LibraryType
    md5: dict[str, str] = Field(default_factory=dict)  # fastq filename -> md5


class ChemistrySpec(_M):
    version: Chemistry
    whitelist_name: str
    whitelist_md5: str
    cb_len: int
    umi_len: int


class Reference(_M):
    genome_build: str  # e.g. GRCh38
    annotation: str  # e.g. GENCODE_v44 / Ensembl_110
    fasta_url: str
    fasta_md5: str
    gtf_url: str
    gtf_md5: str
    sjdb_overhang: int = 90
    star_index_digest: str | None = None  # computed once, content-addressed


class GuideLibrary(_M):
    protospacer_fasta_url: str
    protospacer_md5: str
    guide_to_target_url: str
    guide_to_target_md5: str
    scaffold_seq: str | None = None
    ntc_guide_ids: list[str] = Field(default_factory=list)  # non-targeting controls
    moi: MOIDesign
    expected_guides: int | None = None


class StageImage(_M):
    stage: str  # fetch / fastp / starsolo / guide / cellqc / de
    image: str  # must be name@sha256:...

    @model_validator(mode="after")
    def _pinned(self) -> StageImage:
        if _SHA256 not in self.image:
            raise ValueError(f"stage {self.stage!r}: image must be pinned by @sha256: digest")
        return self


class DEParams(_M):
    model: str = "deseq2"  # deseq2 / edger_qlf
    contrast: str = "target_vs_ntc"
    min_cells_per_perturbation: int = 25  # below this -> "insufficient power", not a p-value
    padj_threshold: float = 0.05


class DatasetManifest(_M):
    dataset_id: str
    title: str
    license: str
    runs: list[RunAccession]
    chemistry: ChemistrySpec
    reference: Reference
    guide_library: GuideLibrary
    images: list[StageImage]
    schema_version: str = MANIFEST_SCHEMA_VERSION
    doi: str | None = None
    geo_series: str | None = None
    aligner: Aligner = Aligner.STARSOLO
    de: DEParams = Field(default_factory=DEParams)
    spot_commit: str | None = None
    seed: int = 0

    @model_validator(mode="after")
    def _gate(self) -> DatasetManifest:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"unsupported manifest schema_version {self.schema_version}")
        if self.license not in ALLOWED_LICENSES:
            raise ValueError(f"license {self.license!r} not in permitted public set")
        libs = {r.library_type for r in self.runs}
        if LibraryType.GEX not in libs:
            raise ValueError("manifest requires at least one GEX library run")
        if LibraryType.GUIDE not in libs:
            raise ValueError("Perturb-seq manifest requires a GUIDE (guide-capture) library run")
        for r in self.runs:
            if not r.md5:
                raise ValueError(f"run {r.accession!r}: per-FASTQ md5 checksums required")
        if not self.guide_library.ntc_guide_ids:
            raise ValueError("guide_library.ntc_guide_ids required (NTCs are the DE reference)")
        return self
