import uuid
from asyncio import Lock
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from pathlib import Path
import re

from document_extractors import DocumentExtractor, ENTIRE_DOCUMENT_CHAPTER, EpubExtractor, PdfExtractor
from indexer import Indexer
from preprocessor import PreProcessor


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
EXAM_CHUNK_SIZE = 1600
EXAM_CHUNK_OVERLAP = 200
MAX_EXAM_SOURCE_CHUNKS = 12


class LibraryError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class UploadResult:
    filename: str
    indexed: list[dict]


class LibraryService:
    """Stores supported source documents and rebuilds the search index."""

    def __init__(
        self,
        resources_dir: Path,
        index_path: Path,
        extractors: Iterable[DocumentExtractor] | None = None,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ):
        self.resources_dir = Path(resources_dir)
        self.index_path = Path(index_path)
        self.max_upload_bytes = max_upload_bytes
        self._extractors = self._build_extractor_registry(extractors or [EpubExtractor(), PdfExtractor()])
        self._catalog_cache: dict[Path, tuple[tuple[int, int], dict]] = {}
        self._lock = Lock()

    def build_index(self) -> list[dict]:
        chunks = []
        for path in self._resource_paths():
            chunks.extend(self._extractors[path.suffix.lower()].extract_chunks(path))

        preprocessor = PreProcessor()
        for chunk in chunks:
            chunk["text"] = preprocessor.process(chunk["text"])

        indexer = Indexer()
        indexed = indexer.index(chunks)
        indexer.save(indexed, self.index_path)
        return indexed

    def list_books(self) -> list[dict]:
        return [self._catalog(path) for path in self._resource_paths()]

    def list_documents(self) -> list[dict]:
        """Return the display catalog for every supported library document."""
        documents = []
        for path in self._resource_paths():
            catalog = self._catalog(path)
            documents.append({
                **catalog,
                "filename": path.name,
                "format": path.suffix.removeprefix(".").lower(),
            })
        return documents

    def load_chapter_text(self, book_title: str, chapter_title: str) -> str:
        return "\n\n".join(chunk["text"] for chunk in self._source_chunks(book_title, chapter_title))

    def load_exam_text(self, book_title: str, chapter_title: str, num_questions: int) -> str:
        source_text = self._format_exam_source(self._source_chunks(book_title, chapter_title))
        exam_chunks = self._split_exam_text(source_text)
        selected_chunks = self._select_evenly_spaced(
            exam_chunks,
            min(num_questions, MAX_EXAM_SOURCE_CHUNKS),
        )
        return "\n\n".join(
            f"Source excerpt {index}:\n{chunk}"
            for index, chunk in enumerate(selected_chunks, start=1)
        )

    def _source_chunks(self, book_title: str, chapter_title: str) -> list[dict]:
        for path in self._resource_paths():
            chunks = self._extractors[path.suffix.lower()].extract_chunks(path)
            title = chunks[0].get("book") if chunks else path.stem
            if title != book_title:
                continue

            if path.suffix.lower() != ".epub" and chapter_title == ENTIRE_DOCUMENT_CHAPTER:
                return chunks

            selected_chunks = [chunk for chunk in chunks if chunk.get("chapter") == chapter_title]
            if not selected_chunks:
                raise ValueError(f"Chapter {chapter_title!r} not found in {book_title!r}")
            return selected_chunks

        raise ValueError(f"Book {book_title!r} not found")

    async def upload(
        self,
        filename: str,
        chunks: AsyncIterable[bytes],
        content_length: str | None = None,
    ) -> UploadResult:
        safe_filename = self._safe_filename(filename)
        if content_length and int(content_length) > self.max_upload_bytes:
            raise LibraryError(413, self._size_error_message())

        self.resources_dir.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            destination = self.resources_dir / safe_filename
            temporary_path = self.resources_dir / f".{uuid.uuid4().hex}.upload"
            size = 0
            try:
                with temporary_path.open("wb") as upload:
                    async for chunk in chunks:
                        size += len(chunk)
                        if size > self.max_upload_bytes:
                            raise LibraryError(413, self._size_error_message())
                        upload.write(chunk)

                if size == 0:
                    raise LibraryError(400, "The uploaded file is empty")

                # Finish reading the incoming upload before replying. Returning
                # while the client is still streaming a duplicate document can
                # make browsers report a network error instead of the 409.
                if destination.exists():
                    raise LibraryError(409, f"A book named {safe_filename} already exists in the library.")

                temporary_path.replace(destination)
                self._catalog_cache.pop(destination, None)
                try:
                    indexed = self.build_index()
                except Exception as exc:
                    destination.unlink(missing_ok=True)
                    raise LibraryError(422, self._invalid_document_message()) from exc

                return UploadResult(filename=destination.name, indexed=indexed)
            finally:
                temporary_path.unlink(missing_ok=True)

    def _safe_filename(self, filename: str) -> str:
        candidate = Path(filename).name
        if not filename or candidate != filename or candidate in {".", ".."}:
            raise LibraryError(400, "A valid filename is required")
        if Path(candidate).suffix.lower() not in self._extractors:
            raise LibraryError(415, self._unsupported_format_message())
        return candidate

    def _resource_paths(self) -> list[Path]:
        if not self.resources_dir.exists():
            return []
        return sorted(
            path
            for path in self.resources_dir.iterdir()
            if path.is_file() and path.suffix.lower() in self._extractors
        )

    def _catalog(self, path: Path) -> dict:
        fingerprint = (path.stat().st_mtime_ns, path.stat().st_size)
        cached = self._catalog_cache.get(path)
        if cached and cached[0] == fingerprint:
            return cached[1]

        catalog = self._extractors[path.suffix.lower()].catalog(path)
        self._catalog_cache[path] = (fingerprint, catalog)
        return catalog

    @staticmethod
    def _split_exam_text(text: str) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > EXAM_CHUNK_SIZE:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(LibraryService._split_long_paragraph(paragraph))
            elif current and len(current) + len(paragraph) + 2 > EXAM_CHUNK_SIZE:
                chunks.append(current)
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}" if current else paragraph
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _split_long_paragraph(paragraph: str) -> list[str]:
        words = paragraph.split()
        chunks = []
        start = 0
        while start < len(words):
            end = start
            length = 0
            while end < len(words):
                extra = len(words[end]) if end == start else len(words[end]) + 1
                if length + extra > EXAM_CHUNK_SIZE and end > start:
                    break
                length += extra
                end += 1
            chunks.append(" ".join(words[start:end]))
            if end >= len(words):
                break

            overlap_start = end
            overlap_length = 0
            while overlap_start > start and overlap_length < EXAM_CHUNK_OVERLAP:
                overlap_start -= 1
                overlap_length += len(words[overlap_start]) + 1
            start = overlap_start if overlap_start > start else end
        return chunks

    @staticmethod
    def _select_evenly_spaced(chunks: list[str], count: int) -> list[str]:
        if len(chunks) <= count:
            return chunks
        if count == 1:
            return [chunks[len(chunks) // 2]]
        return [chunks[round(index * (len(chunks) - 1) / (count - 1))] for index in range(count)]

    @staticmethod
    def _format_exam_source(chunks: list[dict]) -> str:
        parts = []
        previous_chapter = object()
        for chunk in chunks:
            chapter = chunk.get("chapter")
            if chapter and chapter != previous_chapter:
                parts.append(f"{chapter}\n{chunk['text']}")
            else:
                parts.append(chunk["text"])
            previous_chapter = chapter
        return "\n\n".join(parts)

    def _unsupported_format_message(self) -> str:
        extensions = sorted(extension.removeprefix(".").upper() for extension in self._extractors)
        if extensions == ["EPUB"]:
            return "Only EPUB files are supported"
        return f"Only {', '.join(extensions)} files are supported"

    def _size_error_message(self) -> str:
        return f"File must be {self.max_upload_bytes // (1024 * 1024)} MB or smaller"

    def _invalid_document_message(self) -> str:
        extensions = sorted(extension.removeprefix(".").upper() for extension in self._extractors)
        if extensions == ["EPUB"]:
            return "Could not read this EPUB file"
        return "Could not read this document"

    @staticmethod
    def _build_extractor_registry(extractors: Iterable[DocumentExtractor]) -> dict[str, DocumentExtractor]:
        registry: dict[str, DocumentExtractor] = {}
        for extractor in extractors:
            for extension in extractor.extensions:
                normalized_extension = extension.lower()
                if not normalized_extension.startswith("."):
                    raise ValueError("Document extractor extensions must start with a dot")
                if normalized_extension in registry:
                    raise ValueError(f"Multiple extractors registered for {normalized_extension}")
                registry[normalized_extension] = extractor
        if not registry:
            raise ValueError("At least one document extractor is required")
        return registry
