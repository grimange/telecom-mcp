"""Generate replay tests from normalized fixture artifacts."""

from __future__ import annotations

from pathlib import Path


def generate_fixture_tests(*, normalized_dir: Path, tests_dir: Path) -> list[Path]:
    tests_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    templates = {
        "test_ami_parsing.py": "ami_",
        "test_ari_parsing.py": "ari_",
        "test_esl_parsing.py": "esl_",
    }

    json_files = sorted(p for p in normalized_dir.glob("*.json") if p.is_file())

    for filename, prefix in templates.items():
        matches = [p.name for p in json_files if p.name.startswith(prefix)]
        body = _build_test_body(prefix=prefix.rstrip("_"), fixture_names=matches)
        path = tests_dir / filename
        path.write_text(body, encoding="utf-8")
        created.append(path)

    return created


def _build_test_body(*, prefix: str, fixture_names: list[str]) -> str:
    return f'''from __future__ import annotations

import json
from pathlib import Path


def test_{prefix}_fixture_schema() -> None:
    fixture_dir = Path(__file__).resolve().parents[2] / "sanitized"
    fixtures = {fixture_names!r}
    for name in fixtures:
        payload = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
        assert payload["version"] >= 1
        assert "data" in payload
'''
