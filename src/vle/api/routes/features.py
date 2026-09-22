from fastapi import APIRouter, Depends

from vle.api.dependencies import settings
from vle.api.schemas.features import FeaturesResponse

router = APIRouter()


@router.get("/features", response_model=FeaturesResponse)
def get_features(app_settings=Depends(settings)):
    return FeaturesResponse(exam_builder=app_settings.exam_builder_enabled)
