from src.step1_extract.models import SelectorMap, SelectorRecord


def test_selector_map_ids_returns_unique_ids() -> None:
    selector_map = SelectorMap(
        page={"url": "https://example.com"},
        records=[
            SelectorRecord(selector_id="q", selector="input[name='q']", kind="search"),
            SelectorRecord(selector_id="search_btn", selector="button[type='submit']", kind="button"),
        ],
    )

    assert selector_map.selector_ids() == {"q", "search_btn"}
