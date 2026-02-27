"""
Central place for Flask extensions. 

This avoids circular imports and keeps create_app clean. 
Extensions are initialized in create_app() in __init__.py, where the app context is available.
"""


from flask_sqlalchemy import SQLAlchemy 
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect

# Global extension instances - these are imported and initialized in create_app() in __init__.py with the app context.
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()