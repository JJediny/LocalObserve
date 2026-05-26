"""
Pure unit tests for maturity scripts.
No live services required; uses tmp_path fixture.
"""
import json
from pathlib import Path


def _make_fixture_matrix(tmp_path):
    """Write a 3-row fixture matrix.json to tmp_path/.artifacts/matrix.json"""
    rows = [
        {"dimension": "Strategy & Governance", "score": 3},
        {"dimension": "People & Skills", "score": 2},
        {"dimension": "Detection Authoring", "score": 4},
    ]
    artifacts = tmp_path / ".artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    matrix_path = artifacts / "matrix.json"
    matrix_path.write_text(json.dumps(rows), encoding="utf-8")
    return matrix_path


def test_gen_maturity_report_main(tmp_path, monkeypatch):
    """main() should produce a JSON with keys: dimensions, overall_score, generated_at."""
    matrix_path = _make_fixture_matrix(tmp_path)
    out_json = tmp_path / "out" / "report.json"
    out_md = tmp_path / "out" / "report.md"

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts_dir))

    import gen_maturity_report as gmr

    gmr.main(
        argv=[
            "--matrix", str(matrix_path.relative_to(tmp_path)),
            "--out", str(out_json.relative_to(tmp_path)),
            "--md", str(out_md.relative_to(tmp_path)),
            "--caldera", "nonexistent_caldera.json",
        ],
        root_dir=tmp_path
    )

    assert out_json.exists(), "output JSON not created"
    data = json.loads(out_json.read_text())
    for key in ("dimensions", "overall_score", "generated_at"):
        assert key in data, f"missing key {key} in output JSON"
    assert isinstance(data["dimensions"], dict)
    assert data["overall_score"] == 0.9  # (3 + 2 + 4) / 10 total dimensions = 0.9


def test_gen_maturity_assessment_dimensions(tmp_path, monkeypatch):
    """Assessment generator should run main() using root_dir and check REQUIRED_DIMENSIONS."""
    _make_fixture_matrix(tmp_path)

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts_dir))

    import gen_maturity_assessment as gma

    # Run the main assessment generator with tmp_path as root
    gma.main(
        argv=[
            "--matrix", ".artifacts/matrix.json",
            "--out-dir", "docs/reports",
        ],
        root_dir=tmp_path
    )

    out_file = tmp_path / "docs" / "reports" / "maturity-assessment.md"
    assert out_file.exists(), "output markdown not created"
    content = out_file.read_text(encoding="utf-8")

    # Confirm matrix rows are mentioned
    assert "Maturity matrix rows: 3" in content
    # Confirm that dimensions present are mentioned
    assert "Dimension present: Strategy & Governance" in content
    assert "Dimension present: People & Skills" in content
