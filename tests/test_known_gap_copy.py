from pathlib import Path


def test_known_gap_warnings_present() -> None:
    home = Path("src/app/Home.py").read_text(encoding="utf-8")
    assert "Known gaps" in home
    assert "directional" in home
    assert "manual coding" in home
