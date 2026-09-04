from pathlib import Path

import pytest

from source_registry import load_registry, registry_status, source_grade, source_tier, validate_source


def test_bundled_registry_has_verified_tiered_sources():
    registry = load_registry()

    assert registry["version"] == 1
    assert {source["tier"] for source in registry["sources"]} >= {"S", "A", "B", "C"}
    assert any(source["owner"] == "中国证监会" for source in registry["sources"])
    assert any(source["owner"] == "U.S. Securities and Exchange Commission" for source in registry["sources"])
    assert registry["verification"] == {"verified": True, "stable": True, "timeFieldReviewed": True, "ownershipReviewed": True}


def test_source_validator_requires_stable_time_attribution_and_compliance_metadata():
    invalid = {
        "id": "missing-metadata",
        "name": "Example",
        "tier": "A",
        "type": "rss",
        "url": "http://example.test/news",
        "owner": "",
        "timeField": "",
        "attribution": "",
        "compliance": {},
    }

    errors = validate_source(invalid)

    assert "url must use https" in errors
    assert "owner is required" in errors
    assert "timeField is required" in errors
    assert "attribution is required" in errors
    assert "compliance must declare public and redlinePolicy" in errors


def test_source_tier_maps_names_and_unknown_sources_to_conservative_values():
    registry = {
        "sources": [
            {"id": "official", "name": "示例监管机构", "tier": "S"},
            {"id": "media", "name": "示例财经媒体", "tier": "A"},
        ]
    }

    assert source_tier("示例监管机构", registry) == 35
    assert source_tier("示例财经媒体", registry) == 28
    assert source_tier("未知转载", registry) == 8
    assert source_grade("示例监管机构", registry) == "S"
    assert source_grade("未知转载", registry) == "C"
    assert source_tier("假冒监管机构来源", registry) == 8


def test_registry_status_reports_invalid_sources_without_making_them_callable(tmp_path: Path):
    path = tmp_path / "registry.json"
    path.write_text(
        '{"version": 1, "sources": [{"id": "bad", "name": "坏源", "tier": "B", "type": "rss", "url": "https://example.test"}]}',
        encoding="utf-8",
    )

    registry = load_registry(path)
    status = registry_status(registry)

    assert status == {"total": 1, "valid": 0, "invalid": 1, "tiers": {"B": 1}}


def test_load_registry_rejects_malformed_top_level(tmp_path: Path):
    path = tmp_path / "registry.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="registry must be an object"):
        load_registry(path)
