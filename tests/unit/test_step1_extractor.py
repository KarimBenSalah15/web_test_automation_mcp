import pytest

from src.step1_extract.extractor import Step1Extractor
from src.step1_extract.selector_refiner import SelectorRefiner


class _FakeRefiner(SelectorRefiner):
    async def refine(self, *, objective: str, url: str, records: list):
        _ = objective
        _ = url
        _ = records
        return {
            "records": [
                {
                    "selector_id": "search_form",
                    "selector": "#searchForm",
                    "kind": "form",
                    "llm_role": "search_form",
                    "is_fragile": False,
                    "suggested_selector": None,
                },
                {
                    "selector_id": "search_input",
                    "selector": "#q",
                    "kind": "search",
                    "llm_role": "search_input",
                    "is_fragile": False,
                    "suggested_selector": None,
                },
                {
                    "selector_id": "search_submit",
                    "selector": "button[type='submit']",
                    "kind": "button",
                    "llm_role": "search_submit",
                    "is_fragile": True,
                    "suggested_selector": "#searchForm button[type='submit']",
                },
                {
                    "selector_id": "cart_link",
                    "selector": "a[href='/cart']",
                    "kind": "link",
                    "llm_role": "cart_link",
                    "is_fragile": False,
                    "suggested_selector": None,
                },
            ]
        }


@pytest.mark.asyncio
async def test_step1_extractor_builds_selector_map_from_html(monkeypatch) -> None:
    extractor = Step1Extractor(refiner=_FakeRefiner())

    sample_html = """
    <html>
      <body>
        <form id='searchForm'>
          <input id='q' name='q' placeholder='Search products' type='search' />
          <button type='submit'>Search</button>
        </form>
        <a href='/cart'>Cart</a>
      </body>
    </html>
    """

    async def fake_fetch_html(url: str) -> str:
        assert url == "https://example.com"
        return sample_html

    monkeypatch.setattr(extractor, "_fetch_html", fake_fetch_html)

    result = await extractor.run(url="https://example.com", objective="extract selectors")

    selectors = {record.selector for record in result.selector_map.records}
    kinds = {record.kind.value for record in result.selector_map.records}

    assert "#searchForm" in selectors
    assert "#q" in selectors
    assert "button[type='submit']" in selectors
    assert "a[href='/cart']" in selectors
    assert {"form", "search", "button", "link"}.issubset(kinds)
    assert result.rejected_candidates == []
