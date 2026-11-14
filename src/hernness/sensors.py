import ast

FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_MODULES = {"os", "subprocess", "shutil", "socket"}


class DeterministicSensors:
    @staticmethod
    def check_ast_and_security(code: str) -> tuple[bool, list[str]]:
        violations: list[str] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as error:
            return False, [f"SyntaxError at line {error.lineno}: {error.msg}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                        violations.append(f"Forbidden import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in FORBIDDEN_MODULES:
                    violations.append(f"Forbidden import from: {node.module}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                    violations.append(f"Forbidden builtin call: {node.func.id}()")

        return True, violations
