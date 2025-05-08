from app import app
from flask import redirect, render_template, request, url_for, session, flash

@app.route('/')	
@app.route('/index')
def index():
    return render_template('index.html')