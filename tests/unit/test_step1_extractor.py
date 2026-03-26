import pytest

from src.step1_extract.extractor import Step1Extractor
from src.step1_extract.selector_refiner import SelectorRefiner


class _FakeRefiner(SelectorRefiner):
    async def refine(self, *, objective: str, url: str, records: list):
        _ = objective
        _ = url
        refined_records = []
        for record in records:
            refined_records.append(
                {
                    "selector_id": record.selector_id,
                    "selector": record.selector,
                    "kind": record.kind.value,
                    "llm_role": record.selector_id,
                    "is_fragile": False,
                    "suggested_selector": None,
                }
            )

        return {"records": refined_records}


class _InvalidIdRefiner(SelectorRefiner):
    async def refine(self, *, objective: str, url: str, records: list):
        _ = objective
        _ = url
        _ = records
        return {
            "records": [
                {
                    "selector_id": "invented_selector_id",
                    "selector": "#q",
                    "kind": "search",
                    "llm_role": "search_input",
                    "is_fragile": False,
                    "suggested_selector": None,
                }
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


@pytest.mark.asyncio
async def test_step1_extractor_falls_back_to_raw_records_when_llm_records_invalid(monkeypatch) -> None:
    extractor = Step1Extractor(refiner=_InvalidIdRefiner())

    sample_html = """
    <html>
      <body>
        <form id='searchForm'>
          <input id='q' name='q' placeholder='Search products' type='search' />
          <button type='submit'>Search</button>
        </form>
      </body>
    </html>
    """

    async def fake_fetch_html(url: str) -> str:
        assert url == "https://example.com"
        return sample_html

    monkeypatch.setattr(extractor, "_fetch_html", fake_fetch_html)

    result = await extractor.run(url="https://example.com", objective="extract selectors")

    selector_ids = {record.selector_id for record in result.selector_map.records}
    assert len(selector_ids) >= 3
    assert any("selector_id not in extracted set" in reason for reason in result.rejected_candidates)
    assert any("using raw extracted records fallback" in reason for reason in result.rejected_candidates)
