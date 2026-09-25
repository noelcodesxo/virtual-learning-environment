import uuid
from asyncio import Lock
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
import shutil

from vle.library.extractors import DocumentExtractor, ENTIRE_DOCUMENT_CHAPTER, EpubExtractor, PdfExtractor
from vle.rag.indexing import Indexer
from vle.rag.index_loader import load_index
from vle.rag.preprocessing import PreProcessor


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
EXAM_CHUNK_SIZE = 1600
EXAM_CHUNK_OVERLAP = 200
LEGACY_MIGRATION_MARKER = ".legacy-resources-migrated"

logger = logging.getLogger(__name__)


class LibraryError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class UploadResult:
    filename: str
    indexed: list[dict]


@dataclass(frozen=True)
class DeleteResult:
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
        legacy_resources_dir: Path | None = None,
        migration_marker_path: Path | None = None,
    ):
        self.resources_dir = Path(resources_dir)
        self.index_path = Path(index_path)
        self.max_upload_bytes = max_upload_bytes
        self._extractors = self._build_extractor_registry(extractors or [EpubExtractor(), PdfExtractor()])
        self._catalog_cache: dict[Path, tuple[tuple[int, int], dict]] = {}
        self._lock = Lock()
        self.legacy_resources_dir = Path(legacy_resources_dir) if legacy_resources_dir else None
        self.migration_marker_path = (
            Path(migration_marker_path)
            if migration_marker_path
            else self.resources_dir.parent / LEGACY_MIGRATION_MARKER
        )

    def build_index(self) -> list[dict]:
        """Refresh the index while reusing verified persisted source chunks."""
        return self.synchronize_index()

    def initialize(self, index_path: Path | None = None) -> list[dict]:
        """Migrate legacy files once, then bring the persisted index up to date."""
        self._migrate_legacy_resources()
        return self.synchronize_index(index_path)

    def synchronize_index(self, index_path: Path | None = None) -> list[dict]:
        """Incrementally rebuild the persisted index from the current library.

        The existing file remains untouched if extraction or persistence fails.
        """
        output_path = Path(index_path) if index_path else self.index_path
        resources = self._resource_paths()
        existing, requires_rebuild = self._load_existing_index(output_path)
        current_paths = {self._relative_source_path(path): path for path in resources}

        chunks_by_source: dict[str, list[dict]] = {}
        if not requires_rebuild:
            for chunk in existing:
                source_path = chunk.get("source_path")
                if isinstance(source_path, str):
                    chunks_by_source.setdefault(source_path, []).append(chunk)

        reusable_chunks: dict[str, list[dict]] = {}
        for source_path, path in current_paths.items():
            candidate_chunks = chunks_by_source.get(source_path, [])
            digest = self._file_digest(path)
            if not requires_rebuild and self._source_chunks_are_valid(candidate_chunks, source_path, digest):
                reusable_chunks[source_path] = candidate_chunks

        preprocessor = PreProcessor()
        all_chunks: list[dict] = []
        for source_path, path in current_paths.items():
            chunks = reusable_chunks.get(source_path)
            if chunks is None:
                chunks = self._extract_source_chunks(path, source_path, preprocessor)
            all_chunks.extend(sorted(chunks, key=lambda chunk: chunk["source_ordinal"]))

        indexer = Indexer()
        indexed = indexer.index(all_chunks)
        indexer.save(indexed, output_path)
        return indexed

    def _load_existing_index(self, path: Path) -> tuple[list[dict], bool]:
        if not path.exists():
            return [], False
        try:
            loaded = load_index(path)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Could not read persisted library index; rebuilding it: %s", exc)
            return [], True
        if not isinstance(loaded, list) or not all(isinstance(chunk, dict) for chunk in loaded):
            logger.warning("Persisted library index has an invalid shape; rebuilding it")
            return [], True
        if loaded and any("source_path" not in chunk for chunk in loaded):
            logger.info("Persisted library index has no source identity; rebuilding it once")
            return [], True
        return loaded, False

    def _extract_source_chunks(
        self, path: Path, source_path: str, preprocessor: PreProcessor
    ) -> list[dict]:
        digest = self._file_digest(path)
        extracted = self._extractors[path.suffix.lower()].extract_chunks(path)
        expected_count = len(extracted)
        return [
            {
                **chunk,
                "text": preprocessor.process(chunk["text"]),
                "source_path": source_path,
                "source_sha256": digest,
                "source_chunk_count": expected_count,
                "source_ordinal": ordinal,
            }
            for ordinal, chunk in enumerate(extracted)
        ]

    @staticmethod
    def _source_chunks_are_valid(chunks: list[dict], source_path: str, digest: str) -> bool:
        if not chunks:
            return False
        expected_count = len(chunks)
        ordinals: list[int] = []
        for chunk in chunks:
            if (
                chunk.get("source_path") != source_path
                or chunk.get("source_sha256") != digest
                or chunk.get("source_chunk_count") != expected_count
                or not isinstance(chunk.get("source_ordinal"), int)
                or not isinstance(chunk.get("text"), str)
            ):
                return False
            ordinals.append(chunk["source_ordinal"])
        return sorted(ordinals) == list(range(expected_count))

    def _migrate_legacy_resources(self) -> None:
        legacy_dir = self.legacy_resources_dir
        if (
            legacy_dir is None
            or legacy_dir.resolve() == self.resources_dir.resolve()
            or self.migration_marker_path.exists()
        ):
            return

        self.resources_dir.mkdir(parents=True, exist_ok=True)
        if legacy_dir.exists():
            for source in sorted(legacy_dir.iterdir()):
                if not source.is_file() or source.suffix.lower() not in self._extractors:
                    continue
                destination = self.resources_dir / source.name
                if not destination.exists():
                    shutil.copy2(source, destination)
        self.migration_marker_path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_marker_path.touch(exist_ok=False)

    def _relative_source_path(self, path: Path) -> str:
        return path.relative_to(self.resources_dir).as_posix()

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

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
        return "\n\n".join(
            f"Source excerpt {index}:\n{chunk}"
            for index, chunk in enumerate(exam_chunks, start=1)
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

    async def delete(self, filename: str) -> DeleteResult:
        """Remove a library document and refresh the search index."""
        safe_filename = self._safe_filename(filename)
        async with self._lock:
            destination = self.resources_dir / safe_filename
            if not destination.is_file():
                raise LibraryError(404, f"Document {safe_filename} was not found in the library.")

            temporary_path = self.resources_dir / f".{uuid.uuid4().hex}.delete"
            try:
                destination.replace(temporary_path)
                self._catalog_cache.pop(destination, None)
                try:
                    indexed = self.build_index()
                except Exception as exc:
                    temporary_path.replace(destination)
                    raise LibraryError(500, "Could not remove this document") from exc

                return DeleteResult(filename=safe_filename, indexed=indexed)
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
