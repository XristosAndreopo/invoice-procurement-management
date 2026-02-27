"""
Application configuration.
This module defines the configuration settings for the Flask application, including database connection, secret key, 
and other settings. It uses environment variables for sensitive information and defaults for development. In production,
make sure to set the appropriate environment variables and secure the secret key. 
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Base configuration shared by all environments."""

    # IMPORTANT: change this in production
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-please")

    # Database: SQLite for development (simple file in project folder)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'app.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CSRF protection for forms
    WTF_CSRF_ENABLED = True

    # App UI name (used in templates)
    APP_NAME = "Procurement Management"