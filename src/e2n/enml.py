"""ENML content planning helpers for Notion block conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lxml import etree

from e2n.enex import EVERNOTE_LINK_PATTERN, _local_name


DEFAULT_TEXT_BLOCK_LIMIT = 1800
NON_TEXT_TAGS = {"en-media", "object", "iframe", "embed", "audio", "video"}


@dataclass(frozen=True)
class ContentSegment:
    """A planned conversion segment split around non-text ENML content."""

    kind: Literal["text", "evernote_link", "resource"]
    text: str
    value: str = ""


def plan_enml_segments(content: str, text_block_limit: int = DEFAULT_TEXT_BLOCK_LIMIT) -> tuple[ContentSegment, ...]:
    """Split ENML into text chunks and standalone non-text segments.

    Embedded Evernote links and resources are emitted as their own segments. Text
    before and after those segments is preserved as separate text segments.
    """
    if not content.strip():
        return ()
    try:
        root = etree.fromstring(content.encode("utf-8"), parser=etree.XMLParser(recover=True))
    except etree.XMLSyntaxError:
        return _text_segments(content, text_block_limit)

    segments: list[ContentSegment] = []
    _walk_enml(root, segments, text_block_limit)
    return tuple(segment for segment in segments if segment.text or segment.value)


def _walk_enml(element: etree._Element, segments: list[ContentSegment], text_block_limit: int) -> None:
    if element.text:
        segments.extend(_text_segments(element.text, text_block_limit))

    for child in element:
        href = child.attrib.get("href", "")
        tag_name = _local_name(child.tag)
        if tag_name == "a" and EVERNOTE_LINK_PATTERN.match(href):
            link_text = " ".join("".join(child.itertext()).split()) or href
            segments.append(ContentSegment(kind="evernote_link", text=link_text, value=href))
        elif tag_name in NON_TEXT_TAGS:
            segments.append(ContentSegment(kind="resource", text=tag_name, value=_resource_value(child)))
        else:
            _walk_enml(child, segments, text_block_limit)

        if child.tail:
            segments.extend(_text_segments(child.tail, text_block_limit))


def _text_segments(text: str, text_block_limit: int) -> tuple[ContentSegment, ...]:
    normalized = " ".join(text.split())
    if not normalized:
        return ()
    return tuple(ContentSegment(kind="text", text=chunk) for chunk in chunk_text(normalized, text_block_limit))


def chunk_text(text: str, limit: int = DEFAULT_TEXT_BLOCK_LIMIT) -> tuple[str, ...]:
    """Break text into chunks that fit Notion block-size constraints."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    words = text.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(word[start : start + limit] for start in range(0, len(word), limit))
            continue
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return tuple(chunks)


def _resource_value(element: etree._Element) -> str:
    return element.attrib.get("hash") or element.attrib.get("src") or etree.tostring(element, encoding="unicode")
