from fastapi import APIRouter, Depends, HTTPException, Request, status

from vle.api.dependencies import library, require_exam_builder
from vle.api.schemas.library import Book, BooksResponse, DeleteResponse, LibraryDocument, LibraryResponse, UploadResponse
from vle.library.service import LibraryError

router = APIRouter()


@router.post("/library/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_library_file(request: Request, filename: str, service=Depends(library)):
    try:
        result = await service.upload(filename, request.stream(), request.headers.get("content-length"))
    except LibraryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    request.app.state.index = result.indexed
    return UploadResponse(filename=result.filename, indexed_chunks=len(result.indexed))


@router.get("/library", response_model=LibraryResponse)
def list_library_documents(service=Depends(library)):
    return LibraryResponse(documents=[LibraryDocument(**document) for document in service.list_documents()])


@router.delete("/library/{filename}", response_model=DeleteResponse)
async def delete_library_file(request: Request, filename: str, service=Depends(library)):
    try:
        result = await service.delete(filename)
    except LibraryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    request.app.state.index = result.indexed
    return DeleteResponse(filename=result.filename, indexed_chunks=len(result.indexed))


@router.get("/books", response_model=BooksResponse, dependencies=[Depends(require_exam_builder)])
def list_books(service=Depends(library)):
    return BooksResponse(books=[Book(**book) for book in service.list_books()])
