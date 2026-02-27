"""
Entry point for Flask.

Usage (from project root):

    # On Windows (PowerShell):
    $env:FLASK_APP="run.py"
    $env:FLASK_DEBUG="1"
    flask run

or:

    flask --app run.py --debug run 

"""

from app import create_app

# WSGI application object for Flask to run. This is the standard entry point for Flask applications. 
# When you run `flask run`, Flask looks for this `app` variable to start the application.
app = create_app()

if __name__ == "__main__":
    # For direct `python run.py` usage (dev only) - not recommended for production deployment - use `flask run` instead.
    app.run(debug=True)