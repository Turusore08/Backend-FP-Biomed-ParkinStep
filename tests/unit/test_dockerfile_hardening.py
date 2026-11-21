from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_complies_with_cis_and_hadolint_hardening() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "AS builder" in dockerfile
    assert "AS runtime" in dockerfile
    assert "--no-install-recommends" in dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "JWT_SECRET_KEY" not in dockerfile
    assert "POSTGRES_PASSWORD" not in dockerfile


def test_docker_compose_enforces_least_privilege_and_no_hardcoded_secrets() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose
    assert "- ALL" in compose
    assert "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}" in compose
