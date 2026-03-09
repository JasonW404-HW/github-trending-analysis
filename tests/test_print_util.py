from io import StringIO

from src.util.print_util import CustomLogger, banner


def test_logger_info_writes_formatted_line():
    logger = CustomLogger()
    buffer = StringIO()

    logger.info("hello", file=buffer)

    output = buffer.getvalue()
    assert "[INFO]" in output
    assert "hello" in output


def test_logger_rejects_unknown_kwargs():
    logger = CustomLogger()

    try:
        logger.info("x", unknown=True)
    except TypeError as error:
        assert "Unexpected keyword arguments" in str(error)
    else:
        raise AssertionError("Expected TypeError")


def test_banner_wraps_and_draws_box():
    result = banner("hello world", max_width=20)

    lines = result.splitlines()
    assert lines[0].startswith("╔")
    assert lines[-1].startswith("╚")
    assert "hello world" in result


def test_banner_raises_when_width_too_small():
    try:
        banner("x", max_width=3)
    except ValueError as error:
        assert "at least 4" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_banner_raises_when_word_too_long():
    try:
        banner("supercalifragilisticexpialidocious", max_width=10)
    except ValueError as error:
        assert "too long" in str(error)
    else:
        raise AssertionError("Expected ValueError")
