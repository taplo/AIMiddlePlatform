import logging

from src.monitoring.log_buffer import LogBuffer, clear_logs, get_logs, init_log_buffer


def test_log_buffer_maxlen():
    buf = LogBuffer(maxlen=10, level=logging.INFO)
    for i in range(15):
        buf.info("msg %d", i)
    assert len(buf.get_all()) == 10
    assert buf.get_all()[-1]["message"] == "msg 14"


def test_log_buffer_level_filter():
    buf = LogBuffer(maxlen=50, level=logging.WARNING)
    buf.info("should not appear")
    buf.warning("warning msg")
    buf.error("error msg")
    entries = buf.get_all()
    assert len(entries) == 2
    assert entries[0]["level"] == "WARNING"
    assert entries[1]["level"] == "ERROR"


def test_get_logs_empty():
    clear_logs()
    assert get_logs() == {"logs": [], "total": 0}


def test_get_logs_filter_level():
    clear_logs()
    init_log_buffer(maxlen=100)
    logger = logging.getLogger("test_logs")
    logger.warning("warn 1")
    logger.error("err 1")
    logger.info("info 1")
    logger.warning("warn 2")
    result = get_logs(level="WARNING")
    assert result["total"] == 2
    assert all(e["level"] == "WARNING" for e in result["logs"])


def test_get_logs_filter_module():
    clear_logs()
    init_log_buffer(maxlen=100)
    logging.getLogger("mod_a").info("from a")
    logging.getLogger("mod_b").info("from b")
    result = get_logs(module="mod_a")
    assert result["total"] == 1
    assert result["logs"][0]["logger"] == "mod_a"


def test_get_logs_search():
    clear_logs()
    init_log_buffer(maxlen=100)
    logging.getLogger("test").warning("connection timeout to db")
    logging.getLogger("test").info("request succeeded")
    result = get_logs(q="timeout")
    assert result["total"] == 1
    assert "timeout" in result["logs"][0]["message"]
