# extensions.py

from flask_sqlalchemy import SQLAlchemy

# By initializing SQLAlchemy without an app, we can import this 'db' object
# into any part of our application (like blueprints and models) without
# causing circular imports.
db = SQLAlchemy()
