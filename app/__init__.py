# app/__init__.py
from flask import Flask, jsonify
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix
from app.config import Config, validate_config, generate_dev_password
from flask_wtf.csrf import CSRFError
from app.extensions import db, login_manager, socketio, csrf

def _add_column_if_missing(conn, table_columns, table_name, column_name, ddl):
    if column_name not in table_columns:
        conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


def ensure_schema():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    exam_columns = {col['name'] for col in inspector.get_columns('exams')} if 'exams' in table_names else set()
    session_columns = {col['name'] for col in inspector.get_columns('exam_sessions')} if 'exam_sessions' in table_names else set()
    question_columns = {col['name'] for col in inspector.get_columns('questions')} if 'questions' in table_names else set()
    exam_question_columns = {col['name'] for col in inspector.get_columns('exam_questions')} if 'exam_questions' in table_names else set()
    attempt_columns = {col['name'] for col in inspector.get_columns('exam_attempts')} if 'exam_attempts' in table_names else set()
    answer_columns = {col['name'] for col in inspector.get_columns('student_answers')} if 'student_answers' in table_names else set()
    user_columns = {col['name'] for col in inspector.get_columns('users')} if 'users' in table_names else set()
    snapshot_columns = {col['name'] for col in inspector.get_columns('session_question_snapshots')} if 'session_question_snapshots' in table_names else set()
    learning_columns = {col['name'] for col in inspector.get_columns('learnings')} if 'learnings' in table_names else set()
    with db.engine.begin() as conn:
        _add_column_if_missing(conn, exam_columns, 'exams', 'exam_mode', "VARCHAR(30) DEFAULT 'instant_feedback'")
        _add_column_if_missing(conn, exam_columns, 'exams', 'source_bank_id', 'INTEGER')
        _add_column_if_missing(conn, exam_columns, 'exams', 'random_question_count', 'INTEGER')
        _add_column_if_missing(conn, exam_columns, 'exams', 'instructions', 'TEXT')
        _add_column_if_missing(conn, exam_columns, 'exams', 'group_id', 'INTEGER')
        _add_column_if_missing(conn, exam_columns, 'exams', 'status', "VARCHAR(20) DEFAULT 'DRAFT'")
        _add_column_if_missing(conn, exam_columns, 'exams', 'active', 'BOOLEAN DEFAULT 1')
        _add_column_if_missing(conn, exam_columns, 'exams', 'allow_multiple_attempts', 'BOOLEAN DEFAULT 0')
        _add_column_if_missing(conn, exam_columns, 'exams', 'max_attempts', 'INTEGER DEFAULT 1')
        _add_column_if_missing(conn, exam_columns, 'exams', 'created_at', 'DATETIME')
        _add_column_if_missing(conn, exam_columns, 'exams', 'updated_at', 'DATETIME')
        _add_column_if_missing(conn, exam_columns, 'exams', 'auto_remediation', 'BOOLEAN DEFAULT 0')
        _add_column_if_missing(conn, session_columns, 'exam_sessions', 'expected_students', 'INTEGER DEFAULT 0')
        _add_column_if_missing(conn, session_columns, 'exam_sessions', 'question_order', "VARCHAR(20) DEFAULT 'original'")
        _add_column_if_missing(conn, question_columns, 'questions', 'default_points', 'FLOAT DEFAULT 1.0')
        _add_column_if_missing(conn, question_columns, 'questions', 'created_at', 'DATETIME')
        _add_column_if_missing(conn, question_columns, 'questions', 'updated_at', 'DATETIME')
        _add_column_if_missing(conn, question_columns, 'questions', 'video_metadata', 'JSON')
        _add_column_if_missing(conn, snapshot_columns, 'session_question_snapshots', 'video_metadata', 'JSON')
        _add_column_if_missing(conn, exam_question_columns, 'exam_questions', 'order_index', 'INTEGER DEFAULT 1')
        _add_column_if_missing(conn, attempt_columns, 'exam_attempts', 'attempt_number', 'INTEGER DEFAULT 1')
        _add_column_if_missing(conn, attempt_columns, 'exam_attempts', 'earned_points', 'FLOAT DEFAULT 0')
        _add_column_if_missing(conn, attempt_columns, 'exam_attempts', 'max_points', 'FLOAT DEFAULT 0')
        _add_column_if_missing(conn, answer_columns, 'student_answers', 'answer_text', 'TEXT')
        _add_column_if_missing(conn, answer_columns, 'student_answers', 'points_awarded', 'FLOAT DEFAULT 0')
        _add_column_if_missing(conn, answer_columns, 'student_answers', 'question_snapshot_id', 'INTEGER')
        _add_column_if_missing(conn, answer_columns, 'student_answers', 'question_statement', 'TEXT')
        _add_column_if_missing(conn, answer_columns, 'student_answers', 'selected_option_text', 'TEXT')
        _add_column_if_missing(conn, answer_columns, 'student_answers', 'correct_answer_text', 'TEXT')
        _add_column_if_missing(conn, user_columns, 'users', 'default_exam_view', "VARCHAR(40) DEFAULT 'questions'")
        _add_column_if_missing(conn, user_columns, 'users', 'first_name', "VARCHAR(80)")
        _add_column_if_missing(conn, user_columns, 'users', 'last_name', "VARCHAR(80)")
        _add_column_if_missing(conn, user_columns, 'users', 'phone', "VARCHAR(30)")
        _add_column_if_missing(conn, user_columns, 'users', 'institution', "VARCHAR(150)")
        _add_column_if_missing(conn, learning_columns, 'learnings', 'source_session_id', 'INTEGER')

def init_db():
    from app.models import (User, Bank, Question, QuestionOption, Exam, ExamQuestion,
        ExamClass, ExamGroup, Learning, LearningModule, Lesson, Block, LearningProgress,
        BlockAnswer, SessionQuestionSnapshot, Poll, PollVote, LiveAnswer)
    db.create_all()
    ensure_schema()

    # Inicializar o actualizar Superusuario desde configuración (.env)
    superuser_email = Config.SUPERUSER_EMAIL
    superuser_pass = Config.SUPERUSER_PASSWORD
    superuser_name = Config.SUPERUSER_USERNAME

    superuser = User.query.filter((User.email == superuser_email) | (User.role == 'superuser')).first()
    if not superuser:
        generated = not superuser_pass
        superuser_pass = superuser_pass or generate_dev_password()
        superuser = User(username=superuser_name, email=superuser_email, role='superuser')
        superuser.set_password(superuser_pass)
        db.session.add(superuser)
        db.session.commit()
        print(f"Superusuario '{superuser_name}' ({superuser_email}) creado exitosamente.")
        if generated:
            # Solo ocurre en desarrollo: fuera de él validate_config exige SUPERUSER_PASSWORD.
            print(f"  Contraseña temporal generada (no se volverá a mostrar): {superuser_pass}")
    elif Config.SUPERUSER_RESET_ON_BOOT and superuser_pass:
        # Solo en desarrollo por defecto y solo si hay una clave definida en el entorno:
        # en pre-producción la contraseña no debe revertirse en cada reinicio.
        superuser.role = 'superuser'
        superuser.email = superuser_email
        superuser.username = superuser_name
        superuser.set_password(superuser_pass)
        db.session.commit()

    if Config.SEED_DEMO_DATA and not User.query.filter_by(role='instructor').first():
        demo_pass = Config.DEMO_INSTRUCTOR_PASSWORD or generate_dev_password()
        teacher = User(username="Profesor Principal", email="profesor@capacitacion.com", role="instructor")
        teacher.set_password(demo_pass)
        if not Config.DEMO_INSTRUCTOR_PASSWORD:
            print(f"Profesor demo profesor@capacitacion.com — contraseña temporal: {demo_pass}")
        db.session.add(teacher)
        db.session.commit()

        bank = Bank(name="Banco Inicial", description="Preguntas por defecto", created_by=teacher.id)
        db.session.add(bank)
        db.session.commit()

        q1 = Question(
            bank_id=bank.id,
            question_type='multiple_choice',
            statement="¿Cuál es el puerto predeterminado del protocolo HTTP?",
            category="Redes",
            feedback_text="El puerto 80 es la norma para tráfico web no cifrado."
        )
        q2 = Question(
            bank_id=bank.id,
            question_type='multiple_choice',
            statement="¿Qué protocolo de transporte es orientado a conexión?",
            category="Redes",
            feedback_text="TCP garantiza el establecimiento de enlace mediante handshake."
        )
        db.session.add_all([q1, q2])
        db.session.commit()

        db.session.add_all([
            QuestionOption(question_id=q1.id, option_text="80", is_correct=True),
            QuestionOption(question_id=q1.id, option_text="443", is_correct=False),
            QuestionOption(question_id=q2.id, option_text="TCP", is_correct=True),
            QuestionOption(question_id=q2.id, option_text="UDP", is_correct=False),
        ])

        exam = Exam(title="Examen Diagnóstico de Redes", duration_minutes=15, instructor_id=teacher.id)
        db.session.add(exam)
        db.session.commit()

        db.session.add_all([
            ExamQuestion(exam_id=exam.id, question_id=q1.id, points=5.0),
            ExamQuestion(exam_id=exam.id, question_id=q2.id, points=5.0)
        ])
        db.session.commit()
        print("Base de datos inicializada correctamente.")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    validate_config(app.config)

    if app.config.get('PROXY_FIX_HOPS'):
        hops = app.config['PROXY_FIX_HOPS']
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    # Inicializar extensiones
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    # Los handlers de Socket.IO se importan ANTES de init_app: así quedan en
    # socketio.handlers y se registran en cada servidor nuevo (tests, recargas).
    from app.realtime import sockets  # noqa: F401
    from app.blueprints.polls import sockets as poll_sockets  # noqa: F401
    # Lista vacía = solo mismo origen (antes "*", que permitía conectar desde cualquier sitio).
    socketio.init_app(app, cors_allowed_origins=app.config.get('SOCKETIO_CORS_ORIGINS') or None)

    from app.services.video_cues import embed_src, format_timestamp
    app.add_template_filter(format_timestamp, 'mmss')
    app.add_template_global(embed_src, 'video_embed_src')

    with app.app_context():
        init_db()

    # Registrar Blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.questions import questions_bp
    from app.blueprints.exams import exams_bp
    from app.blueprints.media import media_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.learning import learning_bp
    from app.blueprints.polls import polls_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(questions_bp)
    app.register_blueprint(exams_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(learning_bp)
    app.register_blueprint(polls_bp)

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000')
        return response

    @app.errorhandler(CSRFError)
    def _csrf_error(error):
        from flask import flash, redirect, request
        if request.accept_mimetypes.best == 'application/json' or request.is_json:
            return jsonify(error='Token CSRF inválido o ausente. Recarga la página.'), 400
        flash('La página caducó o el formulario no es válido. Inténtalo de nuevo.', 'warning')
        referrer = request.referrer or ''
        # Solo volver a una página propia (evita usar el error como redirección abierta).
        return redirect(referrer if referrer.startswith(request.host_url) else '/'), 302

    @app.errorhandler(413)
    def _too_large(_error):
        limit_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        return jsonify(error=f'Archivo demasiado grande. Límite: {limit_mb} MB.'), 413

    @app.route('/healthz')
    def healthz():
        # Usado por el balanceador / Cloud Run para el chequeo de disponibilidad (SRS: 99.5 %).
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify(status='ok', env=app.config.get('APP_ENV')), 200
        except Exception:
            return jsonify(status='db_unavailable'), 503

    return app

