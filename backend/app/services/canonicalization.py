import json
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from app.schemas.filters import SearchFilters

FIELDS = (
    "supported_languages",
    "genres",
    "categories",
    "tags",
    "developers",
    "publishers",
)

ALIASES = {
    "macos": "mac",
    "osx": "mac",
    "mac os": "mac",
    "win": "windows",
    "ukrainian language": "Ukrainian",
    "українська": "Ukrainian",
    "русский": "Russian",
    "coop": "Co-op",
    "co op": "Co-op",
}


def key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalized.replace("_", " ").replace("-", " ").split())


class CanonicalCatalog:
    def __init__(self, values: dict[str, Iterable[str]] | None = None):
        values = values or {}
        self.values = {field: sorted(set(values.get(field, []))) for field in FIELDS}
        self._maps = {
            field: {key(value): value for value in self.values[field]} for field in FIELDS
        }

    @classmethod
    def load(cls, path: Path) -> "CanonicalCatalog":
        return cls(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8")

    def canonicalize(self, filters: SearchFilters) -> SearchFilters:
        data = filters.model_dump()
        os_values: list[str] = []
        for value in filters.operating_systems:
            normalized = str(ALIASES.get(key(value), key(value))).casefold()
            if normalized in {"windows", "mac", "linux"} and normalized not in os_values:
                os_values.append(normalized)
        data["operating_systems"] = os_values
        for field in FIELDS:
            output: list[str] = []
            for value in getattr(filters, field):
                alias = ALIASES.get(key(value), value)
                canonical = self._maps[field].get(key(str(alias)))
                if canonical and canonical not in output:
                    output.append(canonical)
            data[field] = output
        return SearchFilters.model_validate(data)


class CatalogBuilder:
    def __init__(self):
        self._sets = {field: set() for field in FIELDS}

    def add_payload(self, payload: dict) -> None:
        for field in FIELDS:
            self._sets[field].update(str(value) for value in payload.get(field, []) if value)

    def build(self) -> CanonicalCatalog:
        return CanonicalCatalog(self._sets)
