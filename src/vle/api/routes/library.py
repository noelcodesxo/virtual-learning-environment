from fastapi import APIRouter, HTTPException, Request, status

from vle.api.runtime import library, state
from vle.api.schemas.library import DeleteResponse, LibraryDocument, LibraryResponse, UploadResponse
from vle.library.service import LibraryError

router = APIRouter()


@router.post("/library/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_library_file(request: Request, filename: str):
    try:
        result = await library.upload(filename, request.stream(), request.headers.get("content-length"))
    except LibraryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    state["index"] = result.indexed
    return UploadResponse(filename=result.filename, indexed_chunks=len(result.indexed))


@router.get("/library", response_model=LibraryResponse)
def list_library_documents():
    return LibraryResponse(documents=[LibraryDocument(**document) for document in library.list_documents()])


@router.delete("/library/{filename}", response_model=DeleteResponse)
async def delete_library_file(filename: str):
    try:
        result = await library.delete(filename)
    except LibraryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    state["index"] = result.indexed
    return DeleteResponse(filename=result.filename, indexed_chunks=len(result.indexed))
