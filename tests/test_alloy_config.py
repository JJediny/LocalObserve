from __future__ import annotations

import subprocess
from pathlib import Path

ALLOY_IMAGE = "grafana/alloy@sha256:51aeb9d829239345070619dad3edd6873186f913c84f45b365b74574fcb38ec0"

def test_alloy_config_format(repo_root: Path) -> None:
    config_path = repo_root / "alloy-local-config.yaml"
    result = subprocess.run([
        "docker", "run", "--rm",
        "-v", f"{config_path}:/etc/alloy/config.alloy",
        ALLOY_IMAGE,
        "fmt", "-t", "/etc/alloy/config.alloy"
    ], capture_output=True, text=True)
    assert result.returncode == 0, f"Alloy config is not formatted correctly:\n{result.stderr}"
