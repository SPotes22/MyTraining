import threading
import time
from datetime import datetime
import json
from flask import render_template, request, redirect, url_for, flash, current_app, Response
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.services import audit, password_reset, personal_data
from app.services.mailer import send_mail
from app.models import User, ExamSession, Bank
from app.blueprints.auth import auth_bp

# Bloqueo de fuerza bruta en memoria (suficiente con 1 worker; ver gunicorn.conf.py).
_failed_logins = {}
_failed_lock = threading.Lock()


def _login_key(email):
    return f"{request.remote_addr}|{email}"


def _is_locked_out(email):
    window = current_app.config.get('LOGIN_LOCKOUT_SECONDS', 900)
    limit = current_app.config.get('LOGIN_MAX_ATTEMPTS', 5)
    now = time.monotonic()
    with _failed_lock:
        recent = [t for t in _failed_logins.get(_login_key(email), []) if now - t < window]
        _failed_logins[_login_key(email)] = recent
        return len(recent) >= limit


def _register_failed_login(email):
    with _failed_lock:
        _failed_logins.setdefault(_login_key(email), []).append(time.monotonic())


def _clear_failed_logins(email):
    with _failed_lock:
        _failed_logins.pop(_login_key(email), None)


# RF-028: límite de solicitudes de recuperación por correo (en memoria, 1 worker).
_reset_requests = {}


def _reset_rate_limited(email):
    limit = current_app.config.get('PASSWORD_RESET_MAX_REQUESTS', 3)
    now = time.monotonic()
    with _failed_lock:
        recent = [t for t in _reset_requests.get(email, []) if now - t < 3600]
        limited = len(recent) >= limit
        if not limited:
            recent.append(now)
        _reset_requests[email] = recent
        return limited


@auth_bp.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.role in ['superuser', 'admin']:
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'instructor':
            view = getattr(current_user, 'default_exam_view', 'questions')
            endpoint = {'questions': 'questions.mis_preguntas', 'exams': 'exams.library', 'classes': 'exams.classes', 'learning': 'learning.instructor_dashboard'}.get(view, 'exams.instructor_dashboard')
            return redirect(url_for(endpoint))
        return redirect(url_for('learning.student_catalog'))
    return render_template('landing.html', current_year=datetime.utcnow().year)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and request.method == 'GET':
        return redirect(url_for('auth.home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        if _is_locked_out(email):
            flash('Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.', 'danger')
            return render_template('login.html'), 429

        user = User.query.filter_by(email=email).first()

        if user and user.password_hash and user.check_password(password):
            _clear_failed_logins(email)
            login_user(user)
            display_name = user.first_name or user.username
            if user.role in ['superuser', 'admin']:
                flash(f'Bienvenido Superusuario {display_name}', 'success')
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'instructor':
                flash(f'Bienvenido Profesor {display_name}', 'success')
                view = getattr(user, 'default_exam_view', 'questions')
                endpoint = {'questions': 'questions.mis_preguntas', 'exams': 'exams.library', 'classes': 'exams.classes', 'learning': 'learning.instructor_dashboard'}.get(view, 'exams.instructor_dashboard')
                return redirect(url_for(endpoint))
            else:
                flash(f'Bienvenido(a) {display_name}', 'success')
                return redirect(url_for('learning.student_catalog'))
        
        _register_failed_login(email)
        flash('Credenciales de acceso inválidas', 'danger')
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
@auth_bp.route('/registro', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated and request.method == 'GET':
        return redirect(url_for('auth.home'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        phone = request.form.get('phone', '').strip()
        role_raw = request.form.get('role', 'student').strip().lower()
        institution = request.form.get('institution', '').strip()

        # Validaciones de campos obligatorios
        if not first_name or not last_name or not email or not password:
            flash('Por favor completa todos los campos requeridos: Nombre, Apellido, Correo y Contraseña.', 'warning')
            return render_template('register.html', form_data=request.form)

        if '@' not in email or '.' not in email:
            flash('Por favor ingresa un correo electrónico válido.', 'warning')
            return render_template('register.html', form_data=request.form)

        min_len = current_app.config.get('MIN_PASSWORD_LENGTH', 8)
        if len(password) < min_len:
            flash(f'La contraseña debe tener al menos {min_len} caracteres.', 'warning')
            return render_template('register.html', form_data=request.form)

        if password_confirm and password != password_confirm:
            flash('Las contraseñas no coinciden.', 'warning')
            return render_template('register.html', form_data=request.form)

        # Determinar rol (estudiante o profesor/instructor)
        role = 'instructor' if role_raw in ['instructor', 'profesor', 'teacher', 'docente'] else 'student'
        if role == 'instructor' and not current_app.config.get('ALLOW_INSTRUCTOR_SIGNUP'):
            # RN-09: sin auto-registro de profesores; el administrador los crea.
            role = 'student'

        # Verificar unicidad de correo
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash(f'Ya existe una cuenta registrada con el correo "{email}".', 'danger')
            return render_template('register.html', form_data=request.form)

        full_name = f"{first_name} {last_name}".strip()
        new_user = User(
            username=full_name,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            institution=institution,
            role=role,
            default_exam_view='questions' if role == 'instructor' else 'catalog'
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()  # asigna new_user.id sin cerrar la transacción

        if new_user.role == 'instructor':
            default_bank = Bank(
                name=f"Mi Banco de Preguntas #{new_user.id}",
                description="Banco de preguntas por defecto, creado automáticamente para que puedas empezar a agregar tus preguntas.",
                created_by=new_user.id
            )
            db.session.add(default_bank)

        db.session.commit()

        login_user(new_user)
        display_name = new_user.first_name or new_user.username
        role_label = 'Profesor' if new_user.role == 'instructor' else 'Estudiante'
        flash(f'¡Cuenta creada exitosamente! Bienvenido(a) {role_label} {display_name}.', 'success')

        if new_user.role == 'instructor':
            return redirect(url_for('exams.instructor_dashboard'))
        return redirect(url_for('learning.student_catalog'))

    return render_template('register.html', form_data={})

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@auth_bp.route('/olvide-contrasena', methods=['GET', 'POST'])
def forgot_password():
    """RF-028: pide el correo y envía un enlace de un solo uso, válido 30 minutos."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first() if email else None
        # Misma respuesta exista o no la cuenta: no revela qué correos están registrados.
        if user and user.password_hash and not _reset_rate_limited(email):
            token = password_reset.make_token(user)
            link = url_for('auth.reset_password', token=token, _external=True)
            minutes = current_app.config.get('PASSWORD_RESET_MAX_AGE', 1800) // 60
            send_mail(user.email, 'Recupera tu contraseña de MyTraining',
                      f'Hola {user.first_name or user.username},\n\n'
                      f'Para crear una contraseña nueva abre este enlace (vale {minutes} minutos y sirve una sola vez):\n\n'
                      f'{link}\n\nSi no lo pediste, ignora este correo: tu contraseña no cambia.\n')
            audit.record('auth.password_reset_request', 'user', user.id)
            db.session.commit()
        flash('Si el correo está registrado, te enviamos un enlace para crear una contraseña nueva. Revisa también la carpeta de spam.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = password_reset.verify_token(token)
    if not user:
        flash('El enlace no es válido, ya se usó o caducó. Pide uno nuevo.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        min_len = current_app.config.get('MIN_PASSWORD_LENGTH', 8)
        if len(password) < min_len:
            flash(f'La contraseña debe tener al menos {min_len} caracteres.', 'warning')
        elif password != request.form.get('password_confirm', ''):
            flash('Las contraseñas no coinciden.', 'warning')
        else:
            user.set_password(password)
            audit.record('auth.password_reset', 'user', user.id)
            db.session.commit()
            with _failed_lock:
                for key in [k for k in _failed_logins if k.endswith(f'|{user.email}')]:
                    _failed_logins.pop(key, None)
            flash('Contraseña actualizada. Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('reset_password.html', token=token)


# ── RF-029: derechos del titular ─────────────────────────────────────────────
@auth_bp.route('/perfil', methods=['GET', 'POST'])
@login_required
def profile():
    """Consultar y corregir los propios datos personales."""
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        if current_user.email and not email:
            flash('El correo es obligatorio para las cuentas con contraseña.', 'warning')
            return redirect(url_for('auth.profile'))
        if email and ('@' not in email or '.' not in email):
            flash('Por favor ingresa un correo electrónico válido.', 'warning')
            return redirect(url_for('auth.profile'))
        if email and email != current_user.email and User.query.filter_by(email=email).first():
            flash('Ya existe otra cuenta con ese correo.', 'danger')
            return redirect(url_for('auth.profile'))
        current_user.first_name = first_name or None
        current_user.last_name = last_name or None
        current_user.phone = request.form.get('phone', '').strip() or None
        current_user.institution = request.form.get('institution', '').strip() or None
        if email:
            current_user.email = email
        full_name = f"{first_name} {last_name}".strip()
        if full_name:
            current_user.username = full_name
        audit.record('user.update_profile', 'user', current_user.id)
        db.session.commit()
        flash('Tus datos se actualizaron.', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('profile.html', owns_content=personal_data.owns_content(current_user))


@auth_bp.route('/perfil/contrasena', methods=['POST'])
@login_required
def change_password():
    if not current_user.password_hash or not current_user.check_password(request.form.get('current_password', '')):
        flash('La contraseña actual no es correcta.', 'danger')
        return redirect(url_for('auth.profile'))
    password = request.form.get('password', '')
    min_len = current_app.config.get('MIN_PASSWORD_LENGTH', 8)
    if len(password) < min_len:
        flash(f'La contraseña debe tener al menos {min_len} caracteres.', 'warning')
    elif password != request.form.get('password_confirm', ''):
        flash('Las contraseñas no coinciden.', 'warning')
    else:
        current_user.set_password(password)
        audit.record('auth.password_change', 'user', current_user.id)
        db.session.commit()
        flash('Contraseña actualizada.', 'success')
    return redirect(url_for('auth.profile'))


@auth_bp.route('/perfil/exportar')
@login_required
def export_my_data():
    data = personal_data.export_user_data(current_user)
    audit.record('user.export', 'user', current_user.id, commit=True)
    return Response(json.dumps(data, ensure_ascii=False, indent=2), mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename=mis_datos_mytraining_{current_user.id}.json'})


@auth_bp.route('/perfil/eliminar', methods=['POST'])
@login_required
def delete_my_account():
    """Supresión (anonimización) de la cuenta a pedido del titular."""
    if request.form.get('confirm', '').strip().upper() != 'ELIMINAR':
        flash('Para eliminar tu cuenta escribe ELIMINAR en la casilla de confirmación.', 'warning')
        return redirect(url_for('auth.profile'))
    if current_user.password_hash and not current_user.check_password(request.form.get('current_password', '')):
        flash('La contraseña actual no es correcta.', 'danger')
        return redirect(url_for('auth.profile'))
    if current_user.role in ['superuser', 'admin'] or personal_data.owns_content(current_user):
        flash('Tu cuenta tiene contenido o permisos de administración: un administrador debe gestionar su supresión. '
              'Escríbele al responsable de la plataforma.', 'warning')
        return redirect(url_for('auth.profile'))
    user = current_user._get_current_object()
    audit.record('user.anonymize', 'user', user.id, role=user.role)
    personal_data.anonymize_user(user)
    db.session.commit()
    logout_user()
    flash('Tu cuenta fue eliminada y tus datos personales se borraron. Tus respuestas se conservan sin identificarte.', 'info')
    return redirect(url_for('auth.home'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.home'))

@auth_bp.route('/student/join', methods=['GET', 'POST'])
def student_join_exam():
    if request.method == 'POST':
        student_name = request.form.get('student_name', '').strip()
        code = request.form.get('session_code', '').strip().upper()
        
        if not student_name or not code:
            flash('Debes ingresar tu nombre y un código de examen válido.', 'warning')
            return redirect(url_for('auth.student_join_exam'))

        session_obj = ExamSession.query.filter_by(session_code=code).first()
        if not session_obj:
            flash('Código de examen no encontrado.', 'danger')
            return redirect(url_for('auth.student_join_exam'))

        if session_obj.status in ['finished', 'FINISHED', 'closed', 'CLOSED']:
            flash('Esta sala ya finalizó.', 'danger')
            return redirect(url_for('auth.student_join_exam'))

        user = User(username=student_name, role='student')
        db.session.add(user)
        db.session.commit()
        login_user(user)

        return redirect(url_for('exams.presentar_examen', session_id=session_obj.id))

    return render_template('student_join.html')
