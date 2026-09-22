from fastapi import APIRouter

from vle.api.runtime import EXAM_BUILDER_ENABLED
from vle.api.schemas.features import FeaturesResponse

router = APIRouter()


@router.get("/features", response_model=FeaturesResponse)
def get_features():
    return FeaturesResponse(exam_builder=EXAM_BUILDER_ENABLED)
