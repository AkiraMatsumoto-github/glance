"""マイグレーションのコマンド（本番の反映で deploy/release.sh が打つ alembic upgrade head）。"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_alembic_reads_database_url_from_environment(database_url: str) -> None:
    # 本番と同じく、接続先を環境変数（GLANCE_DATABASE_URL）だけで渡して動くこと
    # （2026-11-28: 設定を SecretStr にしたときに、ここだけ文字列のまま使っていて動かなくなった）
    env = {**os.environ, "GLANCE_DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "(head)" in result.stdout
