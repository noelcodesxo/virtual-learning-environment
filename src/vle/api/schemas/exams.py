from typing import Literal

from pydantic import BaseModel, Field


class GenerateExamRequest(BaseModel):
    source: str
    chapter: str
    num_questions: int = Field(10, ge=1, le=30)
    generated_from: Literal["form", "description"] = "form"
    description: str | None = None


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
    questions: list[ExamQuestion]


class GradeExamRequest(BaseModel):
    answers: dict[str, int]


class ReviewQuestion(ExamQuestion):
    correct_index: int
    why: str
    given_index: int | None


class GradeExamResponse(BaseModel):
    id: str
    source: str
    chapter: str
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


class ExamListResponse(BaseModel):
    exams: list[ExamSummary]


class ExamDetailResponse(BaseModel):
    id: str
    source: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    graded: bool
    questions: list[ExamQuestion] | None = None
    score: int | None = None
    total: int | None = None
    review: list[ReviewQuestion] | None = None
