from pathlib import Path
from typing import Protocol

from ebooklib import epub

from chunker import Chunker


class DocumentExtractor(Protocol):
    extensions: frozenset[str]

    def extract_chunks(self, path: Path) -> list[dict]: ...


class EpubExtractor:
    extensions = frozenset({".epub"})

    def extract_chunks(self, path: Path) -> list[dict]:
        book = epub.read_epub(str(path))
        return Chunker().process_book(book)
