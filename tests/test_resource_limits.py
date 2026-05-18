import yaml
from pathlib import Path

# Services in the localobserve stack that should have memory limits.
# ClamAV is excluded here because it intentionally loads the full virus DB
# into memory (~1GiB) and constraining it causes scan failures.
MEMORY_CONSTRAINED_SERVICES = [
    "openobserve",
    "otel-collector",
    "alert-receiver",
    "dcgm-exporter",
]


def test_stack_services_have_memory_limits(repo_root: Path) -> None:
    """Key localobserve services must declare a mem_limit or deploy.resources limit."""
    compose_path = repo_root / "docker-compose.yaml"
    with compose_path.open() as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})

    for service_name in MEMORY_CONSTRAINED_SERVICES:
        service = services.get(service_name)
        assert service is not None, (
            f"Service '{service_name}' not found in docker-compose.yaml"
        )
        has_mem_limit = "mem_limit" in service
        has_deploy_limit = (
            "deploy" in service
            and "resources" in service["deploy"]
            and "limits" in service["deploy"]["resources"]
            and "memory" in service["deploy"]["resources"]["limits"]
        )
        assert has_mem_limit or has_deploy_limit, (
            f"Service '{service_name}' is missing a memory limit "
            f"(add 'mem_limit' or 'deploy.resources.limits.memory')"
        )
