from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, Field


class PromptMetadata(BaseModel):
    id: str
    version: str
    description: str
    input_schema: str
    output_schema: str
    created_at: date


class PromptRegistry(BaseModel):
    active: dict[str, str] = Field(min_length=1)


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_id: str
    version: str
    system: str
    user: str


class PromptLoader:
    def __init__(self, registry_path: Path):
        self.root = registry_path.parent
        self.registry = PromptRegistry.model_validate(
            yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        )
        self.environment = Environment(undefined=StrictUndefined, autoescape=False)
        self._prompts: dict[str, tuple[PromptMetadata, str, str]] = {}
        for prompt_id, version in self.registry.active.items():
            directory = self.root / prompt_id / version
            metadata = PromptMetadata.model_validate(
                yaml.safe_load((directory / "metadata.yaml").read_text(encoding="utf-8"))
            )
            if metadata.id != prompt_id or metadata.version != version:
                raise ValueError(f"Prompt metadata mismatch for {prompt_id}@{version}")
            system = (directory / "system.jinja2").read_text(encoding="utf-8")
            user = (directory / "user.jinja2").read_text(encoding="utf-8")
            self.environment.parse(system)
            self.environment.parse(user)
            self._prompts[prompt_id] = (metadata, system, user)

    def render(self, prompt_id: str, **context) -> RenderedPrompt:
        try:
            metadata, system, user = self._prompts[prompt_id]
        except KeyError as exc:
            raise KeyError(f"Unknown active prompt: {prompt_id}") from exc
        return RenderedPrompt(
            prompt_id,
            metadata.version,
            self.environment.from_string(system).render(**context),
            self.environment.from_string(user).render(**context),
        )
