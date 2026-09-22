from asyncio import run

from vle.api.app import create_app
from vle.core.config import Settings


def _settings(tmp_path, *, exams_enabled=False):
    return Settings(
        resources_dir=tmp_path / "resources",
        index_path=tmp_path / "index.json",
        exams_dir=tmp_path / "exams",
        ollama_base_url="http://ollama.test",
        default_model="test-model",
        exam_builder_enabled=exams_enabled,
        exam_model="test/exam-model",
    )


def test_lifespan_initializes_empty_library_without_loading_a_stale_index(tmp_path):
    settings = _settings(tmp_path)
    settings.index_path.write_text('[{"text": "stale"}]')
    app = create_app(settings)

    async def exercise_lifespan():
        async with app.router.lifespan_context(app):
            assert app.state.index == []
            assert app.state.exam_jobs.exams == {}

    run(exercise_lifespan())

    assert app.state._state == {}
