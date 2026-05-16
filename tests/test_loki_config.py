from __future__ import annotations

import subprocess
from pathlib import Path

LOKI_IMAGE = "grafana/loki@sha256:73e905b51a7f917f7a1075e4be68759df30226e03dcb3cd2213b989cc0dc8eb4"

def test_loki_config_valid(repo_root: Path) -> None:
    config_path = repo_root / "loki-config.yaml"
    result = subprocess.run([
        "docker", "run", "--rm",
        "-v", f"{config_path}:/etc/loki/config.yaml",
        LOKI_IMAGE,
        "-verify-config", "-config.file=/etc/loki/config.yaml"
    ], capture_output=True, text=True)
    assert result.returncode == 0, f"Loki config is invalid:\n{result.stderr}\n{result.stdout}"
