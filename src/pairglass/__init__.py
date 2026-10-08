"""Pairglass: inspect changes between two paired binary evaluation runs."""

from .core import compare
from .report import render_html, render_markdown

__version__ = "0.1.0"
__all__ = ["compare", "render_html", "render_markdown", "__version__"]
