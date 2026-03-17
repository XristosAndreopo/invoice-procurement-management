"""
app/extensions/__init__.py

Central Flask extension registry for the Invoice / Procurement Management
System.

PURPOSE
-------
This package defines the extension singletons used across the application.

DESIGN RULE
-----------
This module must remain a pure registry.

It may:
- instantiate Flask extension objects
- expose them for import elsewhere

It must NOT:
- initialize extensions with an app
- contain configuration logic
- contain business logic
- contain route logic
"""

from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

__all__ = [
    "db",
    "migrate",
    "login_manager",
    "csrf",
]

