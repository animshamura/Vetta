import logging
import os
import tempfile
import time
from pathlib import Path

from docker.models.containers import Container

import docker

logger = logging.getLogger(__name__)


class DockerSandboxExecutor:
    def __init__(
        self,
        image_name: str,
        timeout_seconds: int = 30,
        memory_limit: str = "512m",
        cpu_quota: int = 50_000,
    ) -> None:
        self.client = docker.from_env()
        self.image_name = image_name
        self.timeout_seconds = timeout_seconds
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota

    def execute_pytest(self, code: str, tests: str) -> tuple[bool, str]:
        container: Container | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="vetta-") as directory:
                workdir = Path(directory)
                os.chmod(workdir, 0o755)
                (workdir / "solution.py").write_text(code, encoding="utf-8")
                (workdir / "test_solution.py").write_text(
                    f"from solution import *\n\n{tests}",
                    encoding="utf-8",
                )

                container = self.client.containers.run(
                    image=self.image_name,
                    command=[
                        "python",
                        "-m",
                        "pytest",
                        "-p",
                        "no:cacheprovider",
                        "-q",
                        "/workspace/test_solution.py",
                    ],
                    volumes={
                        str(workdir.resolve()): {
                            "bind": "/workspace",
                            "mode": "ro",
                        }
                    },
                    working_dir="/workspace",
                    network_disabled=True,
                    mem_limit=self.memory_limit,
                    cpu_period=100_000,
                    cpu_quota=self.cpu_quota,
                    pids_limit=64,
                    read_only=True,
                    tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"],
                    user="10001:10001",
                    detach=True,
                    auto_remove=False,
                )
                deadline = time.monotonic() + self.timeout_seconds
                while time.monotonic() < deadline:
                    container.reload()
                    if container.status in {"exited", "dead"}:
                        break
                    time.sleep(0.1)
                else:
                    container.stop(timeout=2)
                    return False, f"Sandbox timed out after {self.timeout_seconds} seconds."

                output = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                exit_code = container.attrs["State"]["ExitCode"]
                return exit_code == 0, output.strip()
        except docker.errors.DockerException as error:
            logger.exception("Docker sandbox execution failed")
            return False, f"Sandbox execution error: {error}"
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except docker.errors.DockerException:
                    logger.exception("Failed to remove sandbox container")
