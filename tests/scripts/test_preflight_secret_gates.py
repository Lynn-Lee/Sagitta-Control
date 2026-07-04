from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _write_stub(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_preflight_rejects_default_grafana_oauth_secret(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub(
        bin_dir / "docker",
        """#!/usr/bin/env bash
if [[ "$1" == "compose" && "$4" == "ps" ]]; then
  printf '{"State":"running","Health":"healthy"}\\n'
  exit 0
fi
if [[ "$1" == "compose" && "$4" == "exec" ]]; then
  if [[ "$6" == "alembic" && "$7" == "current" ]]; then
    printf '0001_initial\\n'
  elif [[ "$6" == "alembic" && "$7" == "heads" ]]; then
    printf '0001_initial\\n'
  fi
  exit 0
fi
exit 0
""",
    )
    _write_stub(
        bin_dir / "curl",
        """#!/usr/bin/env bash
printf '200'
""",
    )
    _write_stub(
        bin_dir / "lsof",
        """#!/usr/bin/env bash
exit 1
""",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "SECRET_KEY=r4ndom-secret-key-with-48-safe-chars-2026",
                "POSTGRES_PASSWORD=postgres-safe-2026",
                "REDIS_PASSWORD=redis-safe-2026",
                "GRAFANA_CLIENT_SECRET=changeme",
                "LICENSE_PUBLIC_KEY=test-public-key",
                "LICENSE_SERVER_URL=https://license.example.test",
                "LICENSE_ONLINE_GRACE_DAYS=7",
                "APP_INTEGRITY_REQUIRED=true",
                "APP_INTEGRITY_MANIFEST=/app/COMMERCIAL-MANIFEST.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["ENV_FILE"] = str(env_file)

    result = subprocess.run(
        ["bash", str(ROOT / "deploy/preflight-check.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "[FAIL] GRAFANA_CLIENT_SECRET 仍使用默认值" in result.stdout
