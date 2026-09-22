from typing import Literal

from pydantic import BaseModel, Field

from vle.api.runtime import BLOOM_LEVELS


BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


class Book(BaseModel):
    title: str
    chapters: list[str]


class BooksResponse(BaseModel):
    books: list[Book]


class GenerateExamRequest(BaseModel):
    source: str
    chapter: str
    num_questions: int = Field(10, ge=1, le=30)
    generated_from: Literal["form", "description"] = "form"
    description: str | None = None
    bloom_levels: list[BloomLevel] = Field(default_factory=lambda: list(BLOOM_LEVELS), min_length=1)


class ResolveExamDescriptionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=4_000)


class ResolveExamDescriptionResponse(BaseModel):
    source: str
    chapter: str


class ExamQuestion(BaseModel):
    section: str
    question: str
    options: list[str]


class GenerateExamResponse(BaseModel):
    id: str
    source: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    bloom_levels: list[BloomLevel]
    questions: list[ExamQuestion]


JobStatus = Literal["queued", "running", "completed", "failed"]


class ExamJobResponse(BaseModel):
    id: str
    status: JobStatus
    exam_id: str | None
    error: str | None
    created_at: str
    updated_at: str


class ExamJobListResponse(BaseModel):
    jobs: list[ExamJobResponse]


class GradeExamRequest(BaseModel):
    answers: dict[str, int]


class ReviewQuestion(BaseModel):
    section: str
    question: str
    options: list[str]
    correct_index: int
    why: str
    given_index: int | None


class GradeExamResponse(BaseModel):
    id: str
    source: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    bloom_levels: list[BloomLevel]
    score: int
    total: int
    review: list[ReviewQuestion]


class ExamSummary(BaseModel):
    id: str
    source: str
    chapter: str
    created_at: str
    total: int
    score: int | None
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    bloom_levels: list[BloomLevel]


class ExamListResponse(BaseModel):
    exams: list[ExamSummary]


class ExamDetailResponse(BaseModel):
    id: str
    source: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    bloom_levels: list[BloomLevel]
    graded: bool
    questions: list[ExamQuestion] | None = None
    score: int | None = None
    total: int | None = None
    review: list[ReviewQuestion] | None = None
