from pydantic import BaseModel


class FeaturesResponse(BaseModel):
    exam_builder: bool
