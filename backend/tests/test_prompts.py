from pathlib import Path

import pytest

from app.prompts.loader import PromptLoader

pytestmark = pytest.mark.unit


def test_registry_resolves_active_version_and_renders():
    registry = Path(__file__).parents[2] / "prompts" / "registry.yaml"
    loader = PromptLoader(registry)
    prompt = loader.render("query_understanding", query="space games")
    assert prompt.version == "1.0.0"
    assert "space games" in prompt.user


def test_registry_rejects_metadata_mismatch(tmp_path):
    (tmp_path / "registry.yaml").write_text("active:\n  test: 1.0.0\n", encoding="utf-8")
    directory = tmp_path / "test" / "1.0.0"
    directory.mkdir(parents=True)
    (directory / "metadata.yaml").write_text(
        "id: wrong\n"
        "version: 1.0.0\n"
        "description: x\n"
        "input_schema: A\n"
        "output_schema: B\n"
        "created_at: 2026-01-01\n",
        encoding="utf-8",
    )
    (directory / "system.jinja2").write_text("x", encoding="utf-8")
    (directory / "user.jinja2").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="metadata mismatch"):
        PromptLoader(tmp_path / "registry.yaml")
