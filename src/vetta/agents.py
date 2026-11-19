import time

from openai import OpenAI

from vetta.schemas import EvaluationVerdict, HarnessState, MakerArtifact


class MakerAgent:
    def __init__(self, client: OpenAI, model: str) -> None:
        self.client = client
        self.model = model

    def generate_or_patch(self, state: HarnessState) -> MakerArtifact:
        start_time = time.monotonic()
        system_prompt = (
            "You are an enterprise software engineer (MAKER). Write robust Python code and "
            "comprehensive pytest unit tests. Never use os, subprocess, eval, or exec. "
            "Write standalone test_* functions assuming solution functions are already imported."
        )
        user_prompt = f"### SPECIFICATION\n{state.task_spec}\n\n"

        if state.current_iteration > 1:
            user_prompt += f"### PREVIOUS CODE\n```python\n{state.current_code}\n```\n\n"
            if state.last_sensor_report and not state.last_sensor_report.passed:
                user_prompt += (
                    f"### SANDBOX TEST FAILURE\n"
                    f"{state.last_sensor_report.test_output}\n\n"
                )
            if state.last_verdict and not state.last_verdict.approved:
                critiques = "\n".join(
                    f"- [{item.severity}] ({item.category}): {item.description} "
                    f"-> Fix: {item.suggested_fix}"
                    for item in state.last_verdict.critiques
                )
                user_prompt += f"### CHECKER CRITIQUES\n{critiques}\n\n"
            user_prompt += "Address all reported errors completely."

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=MakerArtifact,
            temperature=0.1,
        )
        usage = completion.usage
        state.metrics.total_tokens_used += usage.total_tokens if usage else 0
        state.metrics.maker_calls += 1
        state.metrics.duration_seconds += time.monotonic() - start_time

        artifact = completion.choices[0].message.parsed
        if artifact is None:
            raise RuntimeError("Maker response did not contain a parsed artifact.")
        return artifact


class CheckerAgent:
    def __init__(self, client: OpenAI, model: str) -> None:
        self.client = client
        self.model = model

    def audit(self, state: HarnessState) -> EvaluationVerdict:
        start_time = time.monotonic()
        system_prompt = (
            "You are an adversarial enterprise auditor (CHECKER). You have READ-ONLY access. "
            "Ruthlessly audit the code and unit tests for concurrency bugs, edge case oversights, "
            "and spec violations. Set approved=True ONLY if the code is entirely production-grade."
        )
        sandbox_output = (
            state.last_sensor_report.test_output if state.last_sensor_report else ""
        )
        user_prompt = (
            f"### SPECIFICATION\n{state.task_spec}\n\n"
            f"### SUBMITTED CODE\n```python\n{state.current_code}\n```\n\n"
            f"### SUBMITTED TESTS\n```python\n{state.current_tests}\n```\n\n"
            f"### SANDBOX OUTPUT\n{sandbox_output}\n"
        )
        if "o3" in self.model or "o1" in self.model:
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=EvaluationVerdict,
                reasoning_effort="medium",
            )
        else:
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=EvaluationVerdict,
                temperature=0.0,
            )
        usage = completion.usage
        state.metrics.total_tokens_used += usage.total_tokens if usage else 0
        state.metrics.checker_calls += 1
        state.metrics.duration_seconds += time.monotonic() - start_time

        verdict = completion.choices[0].message.parsed
        if verdict is None:
            raise RuntimeError("Checker response did not contain a parsed verdict.")
        return verdict
