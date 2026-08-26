import json

from index_loader import load_index


def test_load_index_returns_parsed_json_list(tmp_path):
    path = tmp_path / "index.json"
    data = [{"book": "B", "chapter": "Ch1", "section": None, "text": "t", "tf_idf": {"cat": 0.5}}]
    path.write_text(json.dumps(data), encoding="utf-8")

    result = load_index(path)

    assert result == data
