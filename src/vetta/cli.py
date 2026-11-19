import argparse
import logging
from pathlib import Path

from vetta.config import Settings
from vetta.orchestrator import run_harness

DEFAULT_TASK_SPEC = """\
Implement an enterprise-grade ThreadSafeLRUCache in Python:
- __init__(self, capacity: int) with validation (capacity > 0).
- get(self, key) -> Any: returns value or raises KeyError if missing.
- put(self, key, value) -> None: inserts or updates key-value pair, evicting the oldest item
  when capacity is reached.
- Must be thread-safe using threading.Lock.
- O(1) time complexity for both get and put operations.
"""


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 1 or parsed > 10:
        raise argparse.ArgumentTypeError("must be between 1 and 10")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the adversarial code verification harness.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--spec", help="Task specification text.")
    source.add_argument("--spec-file", type=Path, help="Read the task specification from a file.")
    parser.add_argument("--max-iterations", type=positive_int, help="Maximum maker/checker rounds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = Settings()
        settings.validate_openai_credentials()
    except Exception as error:
        parser.error(str(error))

    if args.spec_file:
        try:
            task_spec = args.spec_file.read_text(encoding="utf-8")
        except OSError as error:
            parser.error(f"Could not read specification file: {error}")
    else:
        task_spec = args.spec or DEFAULT_TASK_SPEC

    result = run_harness(
        task_spec,
        args.max_iterations or settings.max_iterations,
        settings,
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.status == "APPROVED" else 1
