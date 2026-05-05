import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scan_no_stubs import scan_for_stubs  # noqa: E402


def write_file(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def messages(root: Path) -> list[str]:
    return [violation.format() for violation in scan_for_stubs([root])]


def test_catches_todo_in_fixture_file(tmp_path: Path) -> None:
    root = tmp_path / "src" / "inferguard"
    write_file(root, "validate/example.py", "def ready() -> bool:\n    return True  # TODO: implement\n")

    found = messages(root)

    assert any("TODO" in message for message in found)


def test_catches_not_implemented_error(tmp_path: Path) -> None:
    root = tmp_path / "src" / "inferguard"
    write_file(root, "validate/example.py", "def ready() -> bool:\n    raise NotImplementedError\n")

    found = messages(root)

    assert any("NotImplementedError" in message for message in found)


def test_catches_pass_as_function_body(tmp_path: Path) -> None:
    root = tmp_path / "src" / "inferguard"
    write_file(root, "validate/example.py", "def ready() -> None:\n    pass\n")

    found = messages(root)

    assert any("pass" in message and "ready" in message for message in found)


def test_honors_allowlist_with_required_reason(tmp_path: Path) -> None:
    root = tmp_path / "src" / "inferguard"
    write_file(
        root,
        "validate/example.py",
        "def ready() -> None:\n    pass  # noqa: scan-no-stubs abstract protocol method\n",
    )

    assert scan_for_stubs([root]) == []


def test_does_not_flag_tests_or_fixtures(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    write_file(root, "tests/test_example.py", "def test_placeholder() -> None:\n    pass\n")
    write_file(root, "tests/fixtures/example.py", "def not_ready() -> None:\n    pass\n")
    write_file(root, "src/inferguard/complete.py", "def ready() -> bool:\n    return True\n")

    assert scan_for_stubs([root]) == []


def test_does_not_flag_unittest_mock_import_in_tests(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    write_file(root, "tests/test_example.py", "from unittest.mock import Mock\n")
    write_file(root, "src/inferguard/complete.py", "def ready() -> bool:\n    return True\n")

    assert scan_for_stubs([root]) == []
