import yaml
from pathlib import Path

def test_loki_containers_have_memory_limits(repo_root: Path) -> None:
    compose_path = repo_root / "docker-compose.yaml"
    with compose_path.open() as f:
        compose = yaml.safe_load(f)
    
    services = compose.get("services", {})
    
    # Assert specific logging containers have limits
    for service_name in ["read", "write", "backend", "alloy"]:
        service = services.get(service_name)
        assert service is not None, f"Service {service_name} not found in docker-compose.yaml"
        assert "mem_limit" in service or "deploy" in service, f"Service {service_name} is missing memory limits"
        
        if "mem_limit" in service:
            assert service["mem_limit"] == "512m", f"Service {service_name} mem_limit is not 512m"
