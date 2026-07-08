"""Tests for the dataset manifest gate (deterministic -> must test)."""

import pytest
from pydantic import ValidationError
from spot_contracts import (
    Aligner,
    Chemistry,
    ChemistrySpec,
    DatasetManifest,
    GuideLibrary,
    LibraryType,
    MOIDesign,
    Reference,
    RunAccession,
    StageImage,
)

IMG = "ghcr.io/spot/starsolo@sha256:" + "a" * 64


def _runs(with_guide: bool = True) -> list[RunAccession]:
    runs = [
        RunAccession(
            accession="SRR1", sample="s1", library_type=LibraryType.GEX, md5={"r1.fq.gz": "x"}
        )
    ]
    if with_guide:
        runs.append(
            RunAccession(
                accession="SRR2", sample="s1", library_type=LibraryType.GUIDE, md5={"g1.fq.gz": "y"}
            )
        )
    return runs


def _manifest(**kw) -> DatasetManifest:
    base = dict(
        dataset_id="marson2025_gwcd4",
        title="Marson CD4 CRISPRi Perturb-seq",
        license="CC-BY-4.0",
        runs=_runs(),
        chemistry=ChemistrySpec(
            version=Chemistry.TENX_V3,
            whitelist_name="3M-feb-2018",
            whitelist_md5="w",
            cb_len=16,
            umi_len=12,
        ),
        reference=Reference(
            genome_build="GRCh38",
            annotation="GENCODE_v44",
            fasta_url="u",
            fasta_md5="a",
            gtf_url="u",
            gtf_md5="b",
        ),
        guide_library=GuideLibrary(
            protospacer_fasta_url="u",
            protospacer_md5="p",
            guide_to_target_url="u",
            guide_to_target_md5="g",
            ntc_guide_ids=["NTC_1"],
            moi=MOIDesign.LOW,
        ),
        images=[StageImage(stage="starsolo", image=IMG)],
        aligner=Aligner.STARSOLO,
    )
    base.update(kw)
    return DatasetManifest(**base)


def test_valid_manifest_passes() -> None:
    assert _manifest().dataset_id == "marson2025_gwcd4"


def test_floating_image_tag_rejected() -> None:
    with pytest.raises(ValidationError):
        StageImage(stage="starsolo", image="ghcr.io/spot/starsolo:latest")


def test_disallowed_license_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(license="proprietary")


def test_missing_guide_library_run_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(runs=_runs(with_guide=False))


def test_missing_md5_rejected() -> None:
    bad = [RunAccession(accession="SRR1", sample="s1", library_type=LibraryType.GEX)]
    bad.append(
        RunAccession(accession="SRR2", sample="s1", library_type=LibraryType.GUIDE, md5={"g": "y"})
    )
    with pytest.raises(ValidationError):
        _manifest(runs=bad)


def test_missing_ntc_rejected() -> None:
    gl = GuideLibrary(
        protospacer_fasta_url="u",
        protospacer_md5="p",
        guide_to_target_url="u",
        guide_to_target_md5="g",
        ntc_guide_ids=[],
        moi=MOIDesign.LOW,
    )
    with pytest.raises(ValidationError):
        _manifest(guide_library=gl)


def test_qc_defaults_and_bad_mito() -> None:
    from spot_contracts import QCParams

    assert QCParams().max_pct_mito == 15.0
    with pytest.raises(ValidationError):
        QCParams(max_pct_mito=150.0)
