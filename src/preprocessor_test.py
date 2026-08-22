from preprocessor import PreProcessor


def test_process_removes_stop_words():
    preprocessor = PreProcessor()
    result = preprocessor.process("the cat")
    assert result == "cat"


def test_process_lowercases_non_stop_words():
    preprocessor = PreProcessor()
    result = preprocessor.process("Hello World")
    assert result == "hello world"


def test_process_returns_empty_string_for_empty_input():
    preprocessor = PreProcessor()
    result = preprocessor.process("")
    assert result == ""


def test_process_all_stop_words_returns_empty_string():
    preprocessor = PreProcessor()
    result = preprocessor.process("a the and")
    assert result == ""


def test_process_no_stop_words_returns_all_lowercased():
    preprocessor = PreProcessor()
    result = preprocessor.process("Quick Brown Fox")
    assert result == "quick brown fox"


def test_process_stop_word_matching_is_case_insensitive():
    preprocessor = PreProcessor()
    result = preprocessor.process("The AND")
    assert result == ""


def test_process_mixed_stop_and_non_stop_words():
    preprocessor = PreProcessor()
    result = preprocessor.process("The Quick Fox")
    assert result == "quick fox"
