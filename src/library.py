import uuid
from asyncio import Lock
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from pathlib import Path

from document_extractors import DocumentExtractor, EpubExtractor
from indexer import Indexer
from preprocessor import PreProcessor


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


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
        self._extractors = self._build_extractor_registry(extractors or [EpubExtractor()])
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
