import pytest
from pydantic import ValidationError

from app.schemas.filters import SearchFilters
from app.services.canonicalization import CanonicalCatalog

pytestmark = pytest.mark.unit


def test_filter_ranges_are_validated():
    with pytest.raises(ValidationError):
        SearchFilters(release_year_from=2025, release_year_to=2020)
    with pytest.raises(ValidationError):
        SearchFilters(minimum_rating_percent=101)


def test_catalog_canonicalizes_aliases_and_drops_invented_values():
    catalog = CanonicalCatalog(
        {"categories": ["Co-op"], "genres": ["Action"], "supported_languages": ["Ukrainian"]}
    )
    result = catalog.canonicalize(
        SearchFilters(
            operating_systems=["Win", "macOS"],
            categories=["coop", "Imaginary"],
            genres=["action"],
            supported_languages=["українська"],
        )
    )
    assert result.operating_systems == ["windows", "mac"]
    assert result.categories == ["Co-op"]
    assert result.genres == ["Action"]
    assert result.supported_languages == ["Ukrainian"]
