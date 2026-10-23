"""Run the development server: ``python app.py`` then open http://127.0.0.1:8000

For hosting, point the WSGI server at ``wsgi.py`` instead (see docs/).
"""

from wsgi import app

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8000, debug=True)
