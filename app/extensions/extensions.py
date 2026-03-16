"""
app/extensions.py

Central Flask extension registry for the Invoice / Procurement Management
System.

PURPOSE
-------
This module defines the extension singletons used across the application.

WHY THIS FILE EXISTS
--------------------
In Flask applications that use the application factory pattern, extensions are
typically created once at module import time and initialized later inside the
factory/bootstrap flow.

This allows the rest of the codebase to import extension objects such as:
- db
- migrate
- login_manager
- csrf

without creating circular initialization problems.

DESIGN RULE
-----------
This module must remain a pure registry.

It may:
- instantiate Flask extension objects
- expose them for import elsewhere

It must NOT:
- initialize extensions with an app
- contain configuration logic
- contain request hooks
- contain business logic
- contain route logic
- contain CLI logic

Those responsibilities belong elsewhere:
- app/bootstrap.py for wiring
- app/__init__.py for app creation
- services/routes/models for application behavior

CURRENT EXTENSIONS
------------------
- db:
    SQLAlchemy database handle

- migrate:
    Flask-Migrate integration for Alembic migrations

- login_manager:
    Flask-Login integration for session-based authentication

- csrf:
    CSRF protection for forms and mutating requests
"""

from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

# -------------------------------------------------------------------
# Database / ORM
# -------------------------------------------------------------------
db = SQLAlchemy()

# -------------------------------------------------------------------
# Database migrations
# -------------------------------------------------------------------
migrate = Migrate()

# -------------------------------------------------------------------
# Authentication session management
# -------------------------------------------------------------------
login_manager = LoginManager()

# -------------------------------------------------------------------
# CSRF protection
# -------------------------------------------------------------------
csrf = CSRFProtect()

__all__ = [
    "db",
    "migrate",
    "login_manager",
    "csrf",
]