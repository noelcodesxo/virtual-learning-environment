import importlib

from vle.api.app import app


def test_api_route_paths_and_methods_remain_compatible():
    included_routes = [
        child
        for route in app.routes
        for child in getattr(getattr(route, "original_router", None), "routes", [route])
    ]
    paths_and_methods = {
        (route.path, method)
        for route in included_routes
        for method in getattr(route, "methods", set()) or set()
        if method not in {"HEAD", "OPTIONS"}
    }

    assert {
        ("/models", "GET"), ("/chat", "POST"), ("/library/upload", "POST"),
        ("/library", "GET"), ("/library/{filename}", "DELETE"), ("/features", "GET"),
        ("/books", "GET"), ("/exams/resolve-description", "POST"), ("/exams", "POST"),
        ("/exams", "GET"), ("/exams/{exam_id}", "GET"), ("/exams/{exam_id}/grade", "POST"),
        ("/exam-jobs", "POST"), ("/exam-jobs", "GET"), ("/exam-jobs/{job_id}", "GET"),
    } <= paths_and_methods


def test_canonical_and_legacy_asgi_entrypoints_export_the_same_app():
    canonical = importlib.import_module("vle.api.app")
    package_compatibility = importlib.import_module("vle.api.server")
    legacy = importlib.import_module("server")

    assert package_compatibility.app is canonical.app
    assert legacy.app is canonical.app
