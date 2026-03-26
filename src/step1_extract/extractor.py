# Primary extractor implementation that fetches the HTML content of the target page,
# parses it to identify interactive elements, and generates candidate selectors for each element. 
# It then applies filtering, refinement, and validation steps to produce a final
# set of selectors mapped to their corresponding interactive elements.
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import httpx

from src.config.schemas import SelectorKind
from src.step1_extract.interactive_filter import InteractiveElementFilter
from src.step1_extract.models import SelectorMapExtractionResult
from src.step1_extract.models import SelectorMap, SelectorRecord
from src.step1_extract.selector_refiner import SelectorRefiner
from src.step1_extract.selector_validator import SelectorValidator


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass(slots=True)
class _DomNode:
    tag: str
    attrs: dict[str, str]
    parent_index: int | None
    nth_of_type: int
    text: str = ""


class _InteractiveDomParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[_DomNode] = []
        self._stack: list[tuple[int, str]] = []
        self._child_tag_counts: dict[int | None, dict[str, int]] = defaultdict(dict)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = (tag or "").lower()
        parent_index = self._stack[-1][0] if self._stack else None

        tag_counts = self._child_tag_counts[parent_index]
        nth_of_type = tag_counts.get(normalized_tag, 0) + 1
        tag_counts[normalized_tag] = nth_of_type

        attr_map = {str(key).lower(): (value or "") for key, value in attrs if key}
        node = _DomNode(
            tag=normalized_tag,
            attrs=attr_map,
            parent_index=parent_index,
            nth_of_type=nth_of_type,
        )
        self.nodes.append(node)
        node_index = len(self.nodes) - 1

        if normalized_tag not in _VOID_TAGS:
            self._stack.append((node_index, normalized_tag))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = (tag or "").lower()
        while self._stack:
            _, stacked_tag = self._stack.pop()
            if stacked_tag == normalized_tag:
                break

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        text = data.strip()
        if not text:
            return

        current_index = self._stack[-1][0]
        existing = self.nodes[current_index].text
        self.nodes[current_index].text = f"{existing} {text}".strip()


class Step1Extractor:
    def __init__(self, *, refiner: SelectorRefiner | None = None) -> None:
        self._filter = InteractiveElementFilter()
        self._validator = SelectorValidator()
        self._refiner = refiner or SelectorRefiner()


    async def run(self, *, url: str, objective: str) -> SelectorMapExtractionResult:
        _ = objective
        html = await self._fetch_html(url)
        nodes = self._parse_html(html)

        candidates = self._build_candidates(nodes)
        pre_filtered = self._filter.filter(candidates)
        rejected: list[str] = []

        try:
            refined_payload = await self._refiner.refine(
                objective=objective,
                url=url,
                records=pre_filtered,
            )
            validated, llm_rejected = self._validator.validate(
                refined_payload=refined_payload,
                extracted_records=pre_filtered,
            )
            rejected.extend(llm_rejected)
        except Exception as exc:
            rejected.append(f"LLM refiner failed; using raw extracted records fallback: {exc}")
            validated = []

        # Keep pipeline alive on real pages: if LLM output cannot be validated,
        # fall back to concrete parser-extracted records.
        if not validated:
            rejected.append(
                "LLM refiner produced 0 valid records; using raw extracted records fallback"
            )
            validated = pre_filtered

        return SelectorMapExtractionResult(
            selector_map=SelectorMap(
                page={"url": url},
                records=validated,
            ),
            rejected_candidates=rejected,
        )

    async def _fetch_html(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def _parse_html(self, html: str) -> list[_DomNode]:
        parser = _InteractiveDomParser()
        parser.feed(html)
        parser.close()
        return parser.nodes

    def _build_candidates(self, nodes: list[_DomNode]) -> list[SelectorRecord]:
        records: list[SelectorRecord] = []
        id_counts: dict[str, int] = defaultdict(int)

        for index, node in enumerate(nodes):
            kind = self._infer_kind(node)
            if kind is None:
                continue

            selector = self._resolve_selector(node_index=index, nodes=nodes)
            label = self._first_non_empty(
                node.attrs.get("aria-label"),
                node.attrs.get("title"),
                node.text,
            )
            seed = self._first_non_empty(
                node.attrs.get("id"),
                node.attrs.get("name"),
                label,
                f"{node.tag}_{index + 1}",
            )
            selector_id = self._build_selector_id(kind=kind, seed=seed, id_counts=id_counts)

            records.append(
                SelectorRecord(
                    selector_id=selector_id,
                    selector=selector,
                    kind=kind,
                    label=label,
                    placeholder=node.attrs.get("placeholder") or None,
                    text=node.text or None,
                    name_attr=node.attrs.get("name") or None,
                    is_visible=not self._is_hidden(node),
                    is_enabled="disabled" not in node.attrs,
                    source_xpath=self._xpath_for_node(node_index=index, nodes=nodes),
                    dom_tag=node.tag,
                    dom_attributes=dict(node.attrs),
                )
            )

        return records

    def _infer_kind(self, node: _DomNode) -> SelectorKind | None:
        tag = node.tag
        role = (node.attrs.get("role") or "").strip().lower()
        input_type = (node.attrs.get("type") or "text").strip().lower()
        hint_blob = " ".join(
            [
                node.attrs.get("name") or "",
                node.attrs.get("id") or "",
                node.attrs.get("aria-label") or "",
                node.attrs.get("placeholder") or "",
            ]
        ).lower()

        if tag == "form":
            return SelectorKind.FORM
        if tag == "button" or role == "button":
            return SelectorKind.BUTTON
        if (tag == "a" and node.attrs.get("href")) or role == "link":
            return SelectorKind.LINK
        if tag == "textarea" or role == "textbox":
            return SelectorKind.TEXTAREA
        if tag == "select" or role == "combobox":
            return SelectorKind.SELECT
        if tag == "input":
            if input_type == "hidden":
                return None
            if input_type == "search" or "search" in hint_blob or "query" in hint_blob:
                return SelectorKind.SEARCH
            return SelectorKind.INPUT
        if role == "searchbox":
            return SelectorKind.SEARCH

        return None

    def _resolve_selector(self, *, node_index: int, nodes: list[_DomNode]) -> str:
        node = nodes[node_index]
        node_id = node.attrs.get("id", "")
        if self._is_valid_css_id(node_id):
            selector = f"#{node_id}"
            if self._count_matches(selector, nodes) == 1:
                return selector

        for attr in ("name", "aria-label", "placeholder", "type", "href", "title"):
            attr_value = node.attrs.get(attr, "")
            if not attr_value:
                continue
            selector = f"{node.tag}[{attr}='{self._escape_selector_value(attr_value)}']"
            if self._count_matches(selector, nodes) == 1:
                return selector

        selector = self._path_selector(node_index=node_index, nodes=nodes)
        if self._count_matches(selector, nodes) == 1:
            return selector

        return f"{selector}"

    def _path_selector(self, *, node_index: int, nodes: list[_DomNode]) -> str:
        parts: list[str] = []
        current_index: int | None = node_index
        while current_index is not None:
            node = nodes[current_index]
            parts.append(f"{node.tag}:nth-of-type({node.nth_of_type})")
            current_index = node.parent_index
        parts.reverse()
        return " > ".join(parts)

    def _count_matches(self, selector: str, nodes: list[_DomNode]) -> int:
        return sum(1 for index in range(len(nodes)) if self._matches_selector(index, selector, nodes))

    def _matches_selector(self, node_index: int, selector: str, nodes: list[_DomNode]) -> bool:
        selector = selector.strip()
        if not selector:
            return False

        node = nodes[node_index]

        if selector.startswith("#"):
            return node.attrs.get("id") == selector[1:]

        attr_match = re.fullmatch(r"([a-z0-9_-]+)\[([a-z0-9_-]+)='(.*)'\]", selector)
        if attr_match:
            tag, attr, value = attr_match.groups()
            return node.tag == tag and node.attrs.get(attr, "") == value.replace("\\'", "'")

        path_match = re.fullmatch(
            r"[a-z0-9_-]+:nth-of-type\(\d+\)(\s>\s[a-z0-9_-]+:nth-of-type\(\d+\))*",
            selector,
        )
        if not path_match:
            return False

        parts = [part.strip() for part in selector.split(">")]
        cursor: int | None = node_index
        for raw_part in reversed(parts):
            part_match = re.fullmatch(r"([a-z0-9_-]+):nth-of-type\((\d+)\)", raw_part)
            if part_match is None or cursor is None:
                return False
            expected_tag, expected_nth = part_match.group(1), int(part_match.group(2))
            cursor_node = nodes[cursor]
            if cursor_node.tag != expected_tag or cursor_node.nth_of_type != expected_nth:
                return False
            cursor = cursor_node.parent_index

        return True

    def _xpath_for_node(self, *, node_index: int, nodes: list[_DomNode]) -> str:
        parts: list[str] = []
        current_index: int | None = node_index
        while current_index is not None:
            node = nodes[current_index]
            parts.append(f"{node.tag}[{node.nth_of_type}]")
            current_index = node.parent_index
        parts.reverse()
        return "/" + "/".join(parts)

    @staticmethod
    def _is_hidden(node: _DomNode) -> bool:
        if "hidden" in node.attrs:
            return True
        if (node.attrs.get("aria-hidden") or "").strip().lower() == "true":
            return True
        if (node.attrs.get("type") or "").strip().lower() == "hidden":
            return True

        style = (node.attrs.get("style") or "").strip().lower()
        if not style:
            return False

        style_map = Step1Extractor._style_to_map(style)
        if style_map.get("display") == "none":
            return True
        if style_map.get("visibility") == "hidden":
            return True
        return False

    @staticmethod
    def _style_to_map(style: str) -> dict[str, str]:
        entries: dict[str, str] = {}
        for declaration in style.split(";"):
            if ":" not in declaration:
                continue
            key, value = declaration.split(":", 1)
            normalized_key = key.strip().lower()
            normalized_value = value.strip().lower()
            if normalized_key:
                entries[normalized_key] = normalized_value
        return entries

    @staticmethod
    def _is_valid_css_id(value: str) -> bool:
        if not value:
            return False
        return re.fullmatch(r"[A-Za-z_][-A-Za-z0-9_:.]*", value) is not None

    @staticmethod
    def _escape_selector_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _first_non_empty(*values: str | None) -> str:
        for value in values:
            if value and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _build_selector_id(*, kind: SelectorKind, seed: str, id_counts: dict[str, int]) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", seed.strip().lower()).strip("_") or "element"
        base = f"{kind.value}_{slug}"
        id_counts[base] += 1
        count = id_counts[base]
        return base if count == 1 else f"{base}_{count}"


# Backward-compatible alias used by existing imports in tests and main.
UnimplementedStep1Extractor = Step1Extractor
