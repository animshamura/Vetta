import logging
import time

from openai import OpenAI

from hernness.agents import CheckerAgent, MakerAgent
from hernness.config import Settings
from hernness.sandbox import DockerSandboxExecutor
from hernness.schemas import HarnessState, SensorReport
from hernness.sensors import DeterministicSensors

logger = logging.getLogger(__name__)


class EnterpriseHarnessOrchestrator:
    def __init__(
        self,
        task_spec: str,
        settings: Settings,
        maker: MakerAgent | None = None,
        checker: CheckerAgent | None = None,
        sandbox: DockerSandboxExecutor | None = None,
    ) -> None:
        self.task_spec = task_spec
        self.settings = settings
        settings.validate_openai_credentials()
        client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
        self.maker = maker or MakerAgent(client, settings.maker_model)
        self.checker = checker or CheckerAgent(client, settings.checker_model)
        self.sandbox = sandbox or DockerSandboxExecutor(
            image_name=settings.sandbox_image,
            timeout_seconds=settings.sandbox_timeout_seconds,
        )

    def run(self, max_iterations: int | None = None) -> HarnessState:
        iteration_limit = max_iterations or self.settings.max_iterations
        state = HarnessState(task_spec=self.task_spec, max_iterations=iteration_limit)
        start_time = time.monotonic()
        logger.info("Starting harness run with a maximum of %d iterations", iteration_limit)

        while state.current_iteration < state.max_iterations:
            state.current_iteration += 1
            logger.info("Starting iteration %d/%d", state.current_iteration, state.max_iterations)
            artifact = self.maker.generate_or_patch(state)
            state.current_code = artifact.code
            state.current_tests = artifact.unit_tests

            ast_valid, violations = DeterministicSensors.check_ast_and_security(state.current_code)
            if not ast_valid or violations:
                state.last_sensor_report = SensorReport(
                    passed=False,
                    ast_valid=ast_valid,
                    security_violations=violations,
                    test_passed=False,
                    test_output="Blocked by static security gate.",
                )
                state.history.append(f"Iter {state.current_iteration}: Static Security Failure")
                continue

            test_passed, test_output = self.sandbox.execute_pytest(
                state.current_code,
                state.current_tests,
            )
            state.last_sensor_report = SensorReport(
                passed=test_passed,
                ast_valid=True,
                security_violations=[],
                test_passed=test_passed,
                test_output=test_output,
            )
            if not test_passed:
                state.history.append(f"Iter {state.current_iteration}: Sandbox Test Failure")
                continue

            verdict = self.checker.audit(state)
            state.last_verdict = verdict
            if verdict.approved:
                state.status = "APPROVED"
                state.history.append(f"Iter {state.current_iteration}: APPROVED")
                break

            state.history.append(f"Iter {state.current_iteration}: REJECTED")

        if state.status != "APPROVED":
            state.status = "FAILED_MAX_RETRIES"
        state.metrics.duration_seconds = time.monotonic() - start_time
        logger.info("Harness run finished with status %s", state.status)
        return state


def run_harness(task_spec: str, max_iterations: int, settings: Settings) -> HarnessState:
    return EnterpriseHarnessOrchestrator(task_spec, settings).run(max_iterations)
