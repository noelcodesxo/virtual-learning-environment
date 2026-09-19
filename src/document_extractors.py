from pathlib import Path
import re
from typing import Protocol

from ebooklib import epub
from pypdf import PdfReader

from chunker import Chunker


ENTIRE_DOCUMENT_CHAPTER = "Entire document"
CHAPTER_TITLE_RE = re.compile(r"^\d+\.")
CONTENTS_HEADER_RE = re.compile(r"^\s*(?:table of )?contents\s*$", re.IGNORECASE | re.MULTILINE)
# A contents page is not limited to book-style "Chapter 1" headings. Research
# papers commonly use entries such as "Abstract", "1 Introduction", and
# "References". The final page number (with optional dot leaders) is the
# reliable part of those entries.
TOC_ENTRY_RE = re.compile(
    r"^\s*(?P<title>.+?)\s*(?:[.\u2026\u00b7\u2022]{2,}\s*|\s+)(?P<page>\d+)\s*$",
    re.MULTILINE,
)
TOC_CHAPTER_HEADING_RE = re.compile(r"^\s*(?P<number>\d+)\.\s+(?P<title>.+?)\s*$")
NUMBERED_TOC_ENTRY_RE = re.compile(
    r"^(?:chapter\s+)?(?P<number>\d+(?:\.\d+)*)(?:\.|\))?(?:\s+|$)",
    re.IGNORECASE,
)
PRINTED_PAGE_RE = re.compile(r"^\s*(\d+)\s*$", re.MULTILINE)
MAX_TOC_SCAN_PAGES = 20
MAX_TOC_CONTINUATION_PAGES = 20


class DocumentExtractor(Protocol):
    extensions: frozenset[str]

    def extract_chunks(self, path: Path) -> list[dict]: ...

    def catalog(self, path: Path) -> dict: ...


class EpubExtractor:
    extensions = frozenset({".epub"})

    def extract_chunks(self, path: Path) -> list[dict]:
        book = epub.read_epub(str(path))
        return Chunker().process_book(book)

    def catalog(self, path: Path) -> dict:
        book = epub.read_epub(str(path))
        chunker = Chunker()
        chapters = [
            title
            for _, _, title, depth in chunker.flatten_toc(book.toc)
            if depth == 0 and CHAPTER_TITLE_RE.match(title)
        ]
        return {"title": chunker.book_title(book) or path.stem, "chapters": chapters}


class PdfExtractor:
    extensions = frozenset({".pdf"})

    def extract_chunks(self, path: Path) -> list[dict]:
        chunker = Chunker()
        reader = PdfReader(str(path))
        outline_entries = self._outline_entries(reader)
        chapter = None
        section = None
        for page_number, page in enumerate(reader.pages):
            for entry_page, title, depth in outline_entries:
                if entry_page != page_number:
                    continue
                if depth == 0:
                    chapter = title
                    section = None
                elif depth == 1:
                    section = title

            text = page.extract_text() or ""
            chunker.chunker_processer(
                text,
                chapter=chapter or f"Page {page_number + 1}",
                section=section,
            )

        if not chunker.chunks:
            raise ValueError("The PDF does not contain extractable text")

        for chunk in chunker.chunks:
            chunk["book"] = path.stem
        return chunker.chunks

    def catalog(self, path: Path) -> dict:
        reader = PdfReader(str(path))
        chapters = [title for _, title, depth in self._outline_entries(reader) if depth == 0]
        return {
            "title": path.stem,
            "chapters": list(dict.fromkeys(chapters)) or [ENTIRE_DOCUMENT_CHAPTER],
        }

    @staticmethod
    def _outline_entries(reader) -> list[tuple[int, str, int]]:
        entries = []

        def walk(nodes, depth=0):
            for node in nodes:
                if isinstance(node, list):
                    walk(node, depth + 1)
                    continue
                title = getattr(node, "title", None)
                try:
                    page_number = reader.get_destination_page_number(node)
                except Exception:
                    continue
                if title and page_number is not None and page_number >= 0:
                    entries.append((page_number, str(title), depth))

        for attribute in ("outline", "outlines"):
            try:
                outline = getattr(reader, attribute)
            except Exception:
                continue
            if outline is None:
                continue
            try:
                walk(outline)
            except Exception:
                # Some PDFs contain a malformed bookmark after valid entries.
                # Keep those valid entries and fall back to the printed TOC only
                # when no usable bookmark was recovered.
                pass
            if entries:
                break

        printed_toc_entries = PdfExtractor._printed_toc_entries(reader)
        if printed_toc_entries and not any(depth == 0 for _, _, depth in entries):
            return printed_toc_entries
        return entries or printed_toc_entries

    @staticmethod
    def _printed_toc_entries(reader) -> list[tuple[int, str, int]]:
        toc_pages = []
        toc_start_page = None
        for page_number, page in enumerate(reader.pages[:MAX_TOC_SCAN_PAGES]):
            text = page.extract_text() or ""
            if CONTENTS_HEADER_RE.search(text):
                toc_start_page = page_number
                toc_pages.append(text)
                break
        if toc_start_page is None:
            return []

        for page_number in range(toc_start_page + 1, min(
            toc_start_page + MAX_TOC_CONTINUATION_PAGES + 1,
            len(reader.pages),
        )):
            text = reader.pages[page_number].extract_text() or ""
            if not TOC_ENTRY_RE.search(text) and not TOC_CHAPTER_HEADING_RE.search(text):
                break
            toc_pages.append(text)

        raw_entries = []
        chapter_headings = []
        for text in toc_pages:
            for line in text.splitlines():
                heading = TOC_CHAPTER_HEADING_RE.fullmatch(line)
                if heading and not TOC_ENTRY_RE.fullmatch(line):
                    chapter_headings.append((heading.group("number"), heading.group("title").strip()))
            for match in TOC_ENTRY_RE.finditer(text):
                title = re.sub(r"\s+", " ", match.group("title")).strip(" .")
                if not title or CONTENTS_HEADER_RE.fullmatch(title):
                    continue
                raw_entries.append((int(match.group("page")), title, PdfExtractor._toc_entry_depth(title)))

        if chapter_headings:
            raw_entries = PdfExtractor._nest_unnumbered_toc_entries(raw_entries)

        printed_page = PRINTED_PAGE_RE.search(toc_pages[0])
        page_offset = (
            toc_start_page - int(printed_page.group(1))
            if printed_page
            else PdfExtractor._toc_page_offset(reader, toc_start_page, raw_entries)
        )
        entries = []
        for page_number, title, depth in raw_entries:
            entries.append((page_number + page_offset, title, depth))

        for number, title in chapter_headings:
            section_prefix = f"{number}."
            section_pages = [
                page_number
                for page_number, section_title, depth in raw_entries
                if depth > 0 and section_title.startswith(section_prefix)
            ]
            if section_pages:
                entries.append((min(section_pages) + page_offset, f"{number}. {title}", 0))

        entries.sort(key=lambda entry: (entry[0], entry[2]))
        return [entry for entry in entries if 0 <= entry[0] < len(reader.pages)]

    @staticmethod
    def _nest_unnumbered_toc_entries(entries: list[tuple[int, str, int]]) -> list[tuple[int, str, int]]:
        """Keep unnumbered labels below explicit numbered chapter headings."""
        nested_entries = []
        previous_numbered_depth = None
        for page_number, title, depth in entries:
            if NUMBERED_TOC_ENTRY_RE.match(title):
                previous_numbered_depth = depth
            elif previous_numbered_depth is not None:
                depth = max(previous_numbered_depth + 1, 1)
            nested_entries.append((page_number, title, depth))
        return nested_entries

    @staticmethod
    def _toc_page_offset(reader, toc_start_page: int, entries: list[tuple[int, str, int]]) -> int:
        """Match a TOC entry in the body when the contents uses Roman numerals."""
        for page_number, title, _ in entries:
            for index in range(toc_start_page + 1, len(reader.pages)):
                text = reader.pages[index].extract_text() or ""
                if CONTENTS_HEADER_RE.search(text):
                    continue
                if title in text:
                    return index - page_number
        return 0

    @staticmethod
    def _toc_entry_depth(title: str) -> int:
        """Return the hierarchy depth encoded in a printed TOC title."""
        match = NUMBERED_TOC_ENTRY_RE.match(title)
        if not match or title.lower().startswith("chapter "):
            return 0
        return match.group("number").count(".")
