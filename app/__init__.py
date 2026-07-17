from flask import Flask
import os

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    
    from app.routes import main
    app.register_blueprint(main)

    return app