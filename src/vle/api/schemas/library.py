from pydantic import BaseModel


class UploadResponse(BaseModel):
    filename: str
    indexed_chunks: int


class DeleteResponse(BaseModel):
    filename: str
    indexed_chunks: int


class LibraryDocument(BaseModel):
    title: str
    filename: str
    format: str
    chapters: list[str]


class LibraryResponse(BaseModel):
    documents: list[LibraryDocument]


class Book(BaseModel):
    title: str
    chapters: list[str]


class BooksResponse(BaseModel):
    books: list[Book]
