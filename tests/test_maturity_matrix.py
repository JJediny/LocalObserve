import json
import os
import pytest

ARTIFACT_PATH = os.path.join(os.path.dirname(__file__), '..', '.artifacts', 'matrix.json')


@pytest.fixture(scope='module')
def matrix_rows():
    if not os.path.exists(ARTIFACT_PATH):
        pytest.fail("Run scripts/run_maturity_check.sh to generate .artifacts/matrix.json before running this test suite")
    with open(ARTIFACT_PATH) as f:
        data = json.load(f)
    return data


def test_matrix_has_min_rows(matrix_rows):
    assert len(matrix_rows) >= 10, f"expected >=10 rows, got {len(matrix_rows)}"


def test_matrix_has_expected_headers(matrix_rows):
    # Each row should have dimension and level columns L0..L3
    sample = matrix_rows[0]
    assert 'dimension' in sample, 'missing "dimension" column'
    for lvl in ['L0_None', 'L1_Experimental', 'L2_Integrated', 'L3_Autonomous']:
        assert lvl in sample, f'missing level column {lvl}'
