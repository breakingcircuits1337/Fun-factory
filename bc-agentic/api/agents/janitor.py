from api.core.sandbox import exec_in_sandbox


async def run_janitor(task_id: str) -> dict:
    """Run pre-merge quality gates: pytest, ruff, mypy, bandit."""
    results = {}

    checks = [
        ("pytest", "cd /workspace && pytest --tb=short -q 2>&1 | tail -20"),
        ("ruff", "cd /workspace && ruff check . 2>&1 | tail -30"),
        ("mypy", "cd /workspace && mypy . --ignore-missing-imports 2>&1 | tail -20"),
        ("bandit", "cd /workspace && bandit -r . -ll 2>&1 | tail -20"),
    ]

    all_passed = True
    for name, cmd in checks:
        result = exec_in_sandbox(task_id, cmd)
        exit_code = result.get("exit_code", -1)
        passed = exit_code == 0
        results[name] = {
            "passed": passed,
            "output": result.get("stdout", "") or result.get("stderr", ""),
            "exit_code": exit_code,
        }
        if not passed:
            all_passed = False

    return {
        "verdict": "pass" if all_passed else "fail",
        "checks": results,
        "summary": "All checks passed" if all_passed else f"Failed: {[k for k, v in results.items() if not v['passed']]}",
    }
