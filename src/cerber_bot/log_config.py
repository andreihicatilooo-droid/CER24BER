import logging
import os


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    log_file = os.getenv("CERBER_LOG_FILE")
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    error_file = os.getenv("CERBER_ERROR_LOG_FILE")
    if error_file and error_file != log_file:
        error_handler = logging.FileHandler(error_file, encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        handlers.append(error_handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)