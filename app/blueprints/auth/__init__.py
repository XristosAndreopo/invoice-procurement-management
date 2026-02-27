"""
Auth blueprint package.

This file just exposes the Blueprint object to be imported in app.__init__. 
The actual routes and logic are in routes.py. 
"""

from .routes import auth_bp  # noqa: F401