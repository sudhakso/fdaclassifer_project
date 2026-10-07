"""FastAPI predictor for Vertex AI custom containers."""

from fda_classifier.serving.app import create_app

__all__ = ["create_app"]
