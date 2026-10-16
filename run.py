# run.py — servidor de desarrollo. En pre-producción usar gunicorn (ver gunicorn.conf.py).
import os
from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == '__main__':
    # El depurador de Werkzeug permite ejecutar código remoto: solo en desarrollo
    # y escuchando en localhost salvo que se pida explícitamente otra interfaz.
    is_dev = app.config.get('APP_ENV') == 'development'
    socketio.run(
        app,
        debug=is_dev and os.environ.get('FLASK_DEBUG', '1') == '1',
        host=os.environ.get('HOST', '127.0.0.1' if is_dev else '0.0.0.0'),
        port=int(os.environ.get('PORT', 5000)),
        allow_unsafe_werkzeug=is_dev,
    )
