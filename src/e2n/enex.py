"""ENEX extraction utilities."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path

from lxml import etree


@dataclass(frozen=True)
class ExtractedNote:
    """A note extracted from an ENEX file."""

    note_id: str
    title: str
    path: Path


@dataclass(frozen=True)
class ProcessingPaths:
    """Filesystem paths for one ENEX processing run."""

    output_directory: Path
    notes_directory: Path
    resources_directory: Path
    master_path: Path
    success_path: Path
    errors_path: Path


@dataclass(frozen=True)
class ExtractionResult:
    """Summary of an ENEX extraction run."""

    source: Path
    output_directory: Path
    total_notes: int
    success_count: int
    error_count: int


def extract_enex_notes(enex_source: Path, processing_directory: Path) -> ExtractionResult:
    """Extract every note from an ENEX file into a named processing directory."""
    source = _validate_enex_file(enex_source)
    paths = _processing_paths(source, processing_directory)
    paths.notes_directory.mkdir(parents=True, exist_ok=True)
    paths.resources_directory.mkdir(parents=True, exist_ok=True)

    total_notes = 0
    success_count = 0
    error_count = 0

    with (
        paths.master_path.open("w", encoding="utf-8") as master_file,
        paths.success_path.open("w", encoding="utf-8") as success_file,
        paths.errors_path.open("w", encoding="utf-8") as errors_file,
    ):
        for note_number, note_element in enumerate(_iter_note_elements(source), start=1):
            total_notes += 1
            note_id = f"note_{note_number:06d}"
            note_file = paths.notes_directory / f"{note_id}.enex"
            title = _note_title(note_element, note_id)
            master_file.write(_note_record(ExtractedNote(note_id=note_id, title=title, path=note_file)))
            try:
                _write_note_file(note_file, note_element)
                success_file.write(_note_record(ExtractedNote(note_id=note_id, title=title, path=note_file)))
                success_count += 1
            except Exception as exc:
                errors_file.write(f"{note_id}\t{title}\t{note_file}\t{exc}\n")
                error_count += 1

    return ExtractionResult(
        source=source,
        output_directory=paths.output_directory,
        total_notes=total_notes,
        success_count=success_count,
        error_count=error_count,
    )


def discover_enex_sources(enex_source: Path) -> list[Path]:
    """Discover one or more ENEX source files from a file or directory path."""
    source = enex_source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"ENEX source does not exist: {source}")
    if source.is_file():
        return [_validate_enex_file(source)]
    if source.is_dir():
        sources = sorted(path for path in source.iterdir() if path.is_file() and path.suffix.lower() == ".enex")
        if not sources:
            raise FileNotFoundError(f"No .enex files found in source directory: {source}")
        return sources
    raise ValueError(f"ENEX source must be a file or directory: {source}")


def _validate_enex_file(enex_source: Path) -> Path:
    """Validate and normalize a single ENEX source file path."""
    source = enex_source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"ENEX source does not exist: {source}")
    if not source.is_file():
        raise ValueError(f"ENEX source is not a file: {source}")
    if source.suffix.lower() != ".enex":
        raise ValueError(f"ENEX source must end with .enex: {source}")
    return source


def _processing_paths(enex_source: Path, processing_directory: Path) -> ProcessingPaths:
    """Build all processing paths for a single ENEX source file."""
    output_directory = processing_directory.expanduser().resolve() / enex_source.stem
    return ProcessingPaths(
        output_directory=output_directory,
        notes_directory=output_directory / "notes",
        resources_directory=output_directory / "resources",
        master_path=output_directory / "master.txt",
        success_path=output_directory / "success.txt",
        errors_path=output_directory / "errors.txt",
    )


def _iter_note_elements(source: Path) -> Iterator[etree._Element]:
    """Yield detached ENEX note elements from a source file."""
    for _event, element in etree.iterparse(str(source), events=("end",), huge_tree=True):
        if _local_name(element.tag) == "note":
            yield element
            element.clear()
            parent = element.getparent()
            if parent is not None:
                while element.getprevious() is not None:
                    del parent[0]


def _local_name(tag: str) -> str:
    """Return an XML tag's local name without a namespace."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _note_title(note_element: etree._Element, fallback: str) -> str:
    """Read a note title from an ENEX note element."""
    for child in note_element:
        if _local_name(child.tag) == "title" and child.text:
            return " ".join(child.text.split())
    return fallback


def _write_note_file(path: Path, note_element: etree._Element) -> None:
    """Write a single note element as a standalone ENEX-shaped XML file."""
    note_xml = etree.tostring(note_element, encoding="utf-8")
    path.write_bytes(b'<?xml version="1.0" encoding="utf-8"?>\n<en-export>\n' + note_xml + b"\n</en-export>\n")


def _note_record(note: ExtractedNote) -> str:
    """Format one note tracking record."""
    return f"{note.note_id}\t{note.title}\t{note.path}\n"
