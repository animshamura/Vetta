from hernness.sensors import DeterministicSensors


def test_syntax_error_is_reported_as_invalid() -> None:
    valid, violations = DeterministicSensors.check_ast_and_security("def broken(:\n    pass")

    assert not valid
    assert violations[0].startswith("SyntaxError at line 1:")


def test_forbidden_imports_and_calls_are_reported() -> None:
    valid, violations = DeterministicSensors.check_ast_and_security(
        "import os\nfrom subprocess import run\nvalue = eval('1')"
    )

    assert valid
    assert violations == [
        "Forbidden import: os",
        "Forbidden import from: subprocess",
        "Forbidden builtin call: eval()",
    ]


def test_safe_code_passes_static_gate() -> None:
    assert DeterministicSensors.check_ast_and_security("def add(a, b):\n    return a + b") == (
        True,
        [],
    )
