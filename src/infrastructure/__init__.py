"""Infrastructure domain exports."""

from src.infrastructure.database import Database
from src.infrastructure.web_generator import WebGenerator

__all__ = ["Database", "WebGenerator"]
