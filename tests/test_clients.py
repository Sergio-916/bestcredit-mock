import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


@pytest.mark.skipif(
    os.environ.get("RUN_CLIENT_CHECKS") != "1", reason="Opt-in: requires sibling Node projects"
)
def test_real_typescript_clients(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    loader = root.parent / "bestcredit4you-leadmanagement/node_modules/tsx/dist/loader.mjs"
    assert loader.is_file(), "Install the sibling lead-management Node dependencies first"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen()
        environment = {**os.environ, "MOCK_DATA_DIR": str(tmp_path), "KOMMO_MOCK_TOKEN": "local-kommo-token"}
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mock_server.app:create_app",
                "--factory",
                "--fd",
                str(listener.fileno()),
                "--log-level",
                "warning",
            ],
            cwd=root,
            env=environment,
            pass_fds=(listener.fileno(),),
        )
        try:
            url = f"http://127.0.0.1:{port}"
            for _ in range(100):
                assert server.poll() is None, "Mock server exited during startup"
                try:
                    if httpx.get(f"{url}/health", timeout=0.1).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.05)
            else:
                pytest.fail("Mock server did not start")
            result = subprocess.run(
                ["node", "--import", str(loader), "scripts/check-clients.mjs"],
                check=False,
                cwd=root,
                env={**environment, "MOCK_BASE_URL": url},
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
