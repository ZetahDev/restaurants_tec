from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import time

import httpx
from sqlalchemy import create_engine, text


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=True)


def _wait_for_http(url: str, timeout_seconds: float = 25.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=1.5)
            if resp.status_code < 500:
                return
        except Exception as exc:  # pragma: no cover - best effort retry loop
            last_error = exc
        time.sleep(0.4)
    raise RuntimeError(f"Server not ready for {url}. last_error={last_error}")


def test_cli_e2e_flow_with_local_api_and_sqlite(tmp_path) -> None:
    root = _repo_root()
    db_path = tmp_path / "e2e_feedbackiq.db"
    report_html = tmp_path / "weekly_report.html"
    report_pdf = tmp_path / "weekly_report.pdf"
    api_port = _free_tcp_port()
    api_base_url = f"http://127.0.0.1:{api_port}"

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path}",
            "API_BASE_URL": api_base_url,
            "OPENAI_API_KEY": "",
            "SLACK_WEBHOOK_URL": "",
            "REPORT_HTML_PATH": str(report_html),
            "REPORT_PDF_PATH": str(report_pdf),
        }
    )

    api_proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "src.api.app:app", "--host", "127.0.0.1", "--port", str(api_port)],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_http(f"{api_base_url}/health")

        _run(["uv", "run", "alembic", "upgrade", "head"], cwd=root, env=env)
        seed_result = _run(["uv", "run", "python", "-m", "src.main", "seed", "--total", "220"], cwd=root, env=env)
        etl_1 = _run(["uv", "run", "python", "-m", "src.main", "etl"], cwd=root, env=env)
        _run(["uv", "run", "python", "-m", "src.main", "alerts"], cwd=root, env=env)
        report_result = _run(["uv", "run", "python", "-m", "src.main", "report"], cwd=root, env=env)

        assert "Seed complete. Inserted surveys:" in seed_result.stdout
        assert "ETL complete |" in etl_1.stdout
        assert "Report complete |" in report_result.stdout
        assert report_html.exists()
        assert report_pdf.exists()

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            surveys_count = conn.execute(text("select count(*) from customer_surveys")).scalar_one()
            unified_before = conn.execute(text("select count(*) from unified_reviews")).scalar_one()
            alerts_count = conn.execute(text("select count(*) from alerts")).scalar_one()

        assert surveys_count >= 220
        assert unified_before > 0
        assert alerts_count > 0

        _run(["uv", "run", "python", "-m", "src.main", "etl"], cwd=root, env=env)
        with engine.begin() as conn:
            unified_after = conn.execute(text("select count(*) from unified_reviews")).scalar_one()

        assert unified_after == unified_before
    finally:
        api_proc.terminate()
        try:
            api_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:  # pragma: no cover - safety kill
            api_proc.kill()

