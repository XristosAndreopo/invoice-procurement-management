"""
app/__init__.py

Flask application factory entrypoint for the Invoice / Procurement Management
System.

PURPOSE
-------
This module is intentionally small.

It is responsible only for:
- creating the Flask application instance
- loading configuration
- delegating application wiring to bootstrap helpers

WHY THIS FILE IS NOW SMALL
--------------------------
In the previous structure, this module also contained:
- navigation metadata
- sidebar visibility helpers
- blueprint registration
- request hooks
- context processors
- CLI registration
- root route registration
- Flask-Login wiring

Those responsibilities have been extracted so this file can remain the single,
clear entrypoint of the application factory.

DESIGN PRINCIPLE
----------------
`app/__init__.py` should answer only one question:

    "How is the Flask app instance created?"

Everything else belongs to dedicated modules.

PUBLIC API
----------
- create_app()

BEHAVIOR
--------
No functional behavior is intended to change through this refactor.
The goal is structural clarity and easier maintenance.
"""

from __future__ import annotations

from flask import Flask

from .bootstrap import configure_app


def create_app() -> Flask:
    """
    Application factory.

    RETURNS
    -------
    Flask
        Fully configured Flask application instance.

    BOOTSTRAP FLOW
    --------------
    1. Create app
    2. Load config
    3. Delegate full wiring to bootstrap helpers
    """
    app = Flask(__name__)
    app.config.from_object("config.Config")
    configure_app(app)
    return app

