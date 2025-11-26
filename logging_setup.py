import logging
import logging.handlers

# Configure logging with rotation (self-cleaning)
logging.basicConfig(
    # Default to INFO so we don't flood logs with token-level debug noise.
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            "app.log",
            maxBytes=1_000_000,  # ~1MB per file
            backupCount=3,       # keep last 3 rotations
            encoding="utf-8",
        ),
    ],
)


def get_logger(name):
    return logging.getLogger(name)
