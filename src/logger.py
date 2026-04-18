import logging

from pythonjsonlogger import jsonlogger


def get_logger(name: str, run_id: str = None) -> logging.Logger:
    """Return a logger that emits one JSON object per line.

    The field names (timestamp, level, event) match what GCP Cloud Logging
    uses for structured indexing — rename_fields does the translation.

    The `if not logger.handlers` guard prevents duplicate handlers when
    get_logger() is called multiple times with the same name: Python's logging
    module caches logger instances by name, so without the guard each call
    would stack another StreamHandler and every event would print N times.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(
            fmt='%(asctime)s %(name)s %(levelname)s %(message)s',
            rename_fields={
                'asctime': 'timestamp',
                'levelname': 'level',
                'message': 'event',
            }
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
