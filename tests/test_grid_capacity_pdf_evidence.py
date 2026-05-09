"""Cross-check the qualitative claims behind grid_capacity_heatmap.geojson
against the actual content of the PDFs in data/raw/.

`tests/test_grid_capacity_data.py` validates the GeoJSON has the tiers we
*claim* match the source PDFs. This test goes one step further: it opens
each cited PDF with pypdf, extracts text, and asserts that the keywords
supporting each tier classification actually appear. If a researcher
later changes the GeoJSON to cite a PDF that doesn't substantiate the
tier (e.g. cites a wind-power plan as evidence for SE3 capacity), the
test fails.

Limitations: text extraction is keyword-level, not semantic. We can
catch "this PDF doesn't even mention SE3" but not "this PDF mentions SE3
in a different context than what the GeoJSON implies." For deeper
verification, a researcher reads the cited page in the PDF; this test is
a guardrail, not a substitute.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")


RAW_DIR = Path("data/raw")

PDFS = {
    "svk_nup": "svk_natutveckling_nup_2026-2035.pdf",
    "svk_nordsyd": "svenska-kraftnats-investeringspaket-nordsyd.pdf",
    "ellevio": "ellevios-natutvecklingsplan-2025-2034.pdf",
    "vattenfall": "vattenfall-eldistributions-natutvecklingsplan-2025-2034.pdf",
}


@lru_cache(maxsize=8)
def _full_text(pdf_filename: str) -> str:
    """Return the lowercased concatenated text of a PDF in data/raw/.

    Cached so re-reads across tests don't reparse the same 50-page document.
    """
    path = RAW_DIR / pdf_filename
    reader = pypdf.PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
    return "\n".join(chunks).lower()


def _count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text))


# === SE1 ample (per Svk NUP) ===
def test_svk_nup_documents_se1_export_framing() -> None:
    """The SE1-ample tier is cited to Svk NUP. The PDF must mention SE1
    AND a north-region (Norrbotten) AND export/overskott framing."""
    text = _full_text(PDFS["svk_nup"])
    assert _count(text, r"\bse\s?1\b") >= 5, "Svk NUP must reference SE1 multiple times"
    assert _count(text, r"norrbotten") >= 5, "Svk NUP must reference Norrbotten"
    # SE1/SE2 are net-export hydro regions in any Svk capacity-context document
    assert _count(text, r"\bexport\b|överskott|overskott") >= 1, (
        "Svk NUP must contain export/overskott framing somewhere"
    )


# === SE2 ample (per Svk NUP) ===
def test_svk_nup_documents_se2_and_north_regions() -> None:
    text = _full_text(PDFS["svk_nup"])
    assert _count(text, r"\bse\s?2\b") >= 5, "Svk NUP must reference SE2"
    assert _count(text, r"v[äa]sterbotten") >= 5, "Svk NUP must reference Västerbotten"


# === SE3 surround constrained (per Svk NUP + north-south investment package) ===
def test_svk_nup_documents_se3_and_north_south_corridor() -> None:
    text = _full_text(PDFS["svk_nup"])
    assert _count(text, r"\bse\s?3\b") >= 5, "Svk NUP must reference SE3"
    assert _count(text, r"nord[\s-]?syd|nord[\s-]?-?syd"), (
        "Svk NUP must discuss the north-south corridor — that's what "
        "drives the SE3-constrained classification"
    )


def test_svk_nordsyd_is_predominantly_about_north_south_corridor() -> None:
    """svenska-kraftnats-investeringspaket-nordsyd.pdf is cited as
    primary evidence for the SE3 deficit framing. The investment package
    document must therefore discuss the north-south corridor heavily."""
    text = _full_text(PDFS["svk_nordsyd"])
    assert _count(text, r"nord[\s-]?syd|nord[\s-]?-?syd") >= 10, (
        "Investment-package PDF must reference 'nord-syd' frequently — "
        "if it doesn't, the citation is wrong"
    )
    assert _count(text, r"f[öo]rst[äa]rk") >= 1, "Must discuss reinforcement"


# === SE3 Stockholm/Mälardalen red (per Vattenfall + Ellevio DSO plans) ===
def test_vattenfall_documents_stockholm_capacity_constraint() -> None:
    """The Stockholm tier-0 polygon is cited to Vattenfall's DSO plan.
    The PDF must mention Stockholm AND capacity / reinforcement / shortage
    language alongside it."""
    text = _full_text(PDFS["vattenfall"])
    assert _count(text, r"stockholm") >= 5, "Vattenfall plan must reference Stockholm"
    assert _count(text, r"f[öo]rst[äa]rk") >= 5, (
        "Vattenfall plan must discuss reinforcement (förstärkning)"
    )
    # Vattenfall specifically — the keyword scan showed kapacitetsbrist appears here
    assert _count(text, r"kapacitetsbrist|underskott|brist"), (
        "Vattenfall plan must mention capacity shortage / brist somewhere — "
        "if it doesn't, the Stockholm tier-0 citation is wrong"
    )


def test_ellevio_documents_stockholm_priority() -> None:
    """Ellevio's DSO plan is also cited for the Stockholm tier-0 polygon.
    Ellevio's footprint is central Sweden — the plan must mention
    Stockholm and reinforcement priorities."""
    text = _full_text(PDFS["ellevio"])
    assert _count(text, r"stockholm") >= 5, "Ellevio plan must reference Stockholm"
    assert _count(text, r"f[öo]rst[äa]rk") >= 5, (
        "Ellevio plan must discuss reinforcement"
    )


# === SE4 red (per Svk NUP) ===
def test_svk_nup_documents_se4_and_southern_regions() -> None:
    text = _full_text(PDFS["svk_nup"])
    assert _count(text, r"\bse\s?4\b") >= 5, "Svk NUP must reference SE4"
    # Skåne and Blekinge are the SE4 regions — must appear if SE4 is discussed
    skane_or_blekinge = _count(text, r"sk[åa]ne") + _count(text, r"blekinge")
    assert skane_or_blekinge >= 5, "Svk NUP must reference Skåne / Blekinge for SE4"
    assert _count(text, r"\bimport\b|underskott"), (
        "Svk NUP must discuss import/underskott framing alongside SE4"
    )


# === Generic robustness ===
@pytest.mark.parametrize("pdf_filename", list(PDFS.values()))
def test_each_cited_pdf_extracts_meaningful_text(pdf_filename: str) -> None:
    """If a PDF is image-only / unparseable, downstream evidence checks
    are vacuous. Guard against silently regressing into a state where
    keyword scans return zero hits because there's no text to scan."""
    text = _full_text(pdf_filename)
    assert len(text) > 5000, (
        f"{pdf_filename} extracted only {len(text)} chars — "
        "PDF may be image-only / scanned. Re-source or run OCR before "
        "trusting the evidence tests above."
    )


def test_no_unsubstantiated_pdf_citations_in_geojson() -> None:
    """For every PDF cited by the GeoJSON, the PDF must contain at least
    SOME of the keywords the cited tier rests on (SE1-4, Stockholm,
    nord-syd, kapacitet, förstärkning). If a PDF cites zero of these,
    the citation is suspect."""
    import json
    geo = json.loads(Path("data/manual/grid_capacity_heatmap.geojson").read_text())
    cited: set[str] = set()
    for f in geo["features"]:
        for token in str(f["properties"]["source_pdf"]).split(";"):
            cited.add(token.strip())
    cited &= set(PDFS.values())  # only check PDFs we have

    keywords_pat = re.compile(
        r"\bse\s?[1-4]\b|stockholm|nord[\s-]?syd|kapacitet|f[öo]rst[äa]rk",
        re.IGNORECASE,
    )
    for pdf_name in cited:
        text = _full_text(pdf_name)
        assert keywords_pat.search(text), (
            f"{pdf_name} contains none of the supporting keywords — "
            "either the citation is wrong or text extraction failed"
        )
