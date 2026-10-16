from functools import wraps
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Exam, ExamSession, Bank, ExamClass, ExamGroup, Learning
from app.blueprints.admin import admin_bp

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['superuser', 'admin']:
            flash('Acceso denegado: se requieren permisos de Superusuario.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    instructors = User.query.filter_by(role='instructor').order_by(User.id.desc()).all()
    total_exams = Exam.query.count()
    total_sessions = ExamSession.query.count()
    total_students = User.query.filter_by(role='student').count()
    return render_template(
        'admin_dashboard.html',
        instructors=instructors,
        total_exams=total_exams,
        total_sessions=total_sessions,
        total_students=total_students
    )

@admin_bp.route('/instructor/create', methods=['POST'])
@login_required
@admin_required
def create_instructor():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()

    if not username or not email or not password:
        flash('Todos los campos son obligatorios.', 'warning')
        return redirect(url_for('admin.dashboard'))

    min_len = current_app.config.get('MIN_PASSWORD_LENGTH', 8)
    if len(password) < min_len:
        flash(f'La contraseña debe tener al menos {min_len} caracteres.', 'warning')
        return redirect(url_for('admin.dashboard'))

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash(f'Ya existe un usuario registrado con el correo "{email}".', 'danger')
        return redirect(url_for('admin.dashboard'))

    instructor = User(username=username, email=email, role='instructor')
    instructor.set_password(password)
    db.session.add(instructor)
    db.session.commit()

    flash(f'Cuenta de profesor "{username}" ({email}) creada exitosamente.', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/instructor/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_instructor(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != 'instructor':
        flash('No se puede eliminar un usuario que no sea profesor.', 'warning')
        return redirect(url_for('admin.dashboard'))

    # SQLite reutiliza el id más alto al borrar: si el profesor tenía contenido, el
    # siguiente usuario creado heredaría sus exámenes, bancos y resultados de estudiantes.
    # (En PostgreSQL este borrado además fallaría por llaves foráneas.)
    owns_content = any(model.query.filter_by(**{field: user.id}).first() for model, field in [
        (Exam, 'instructor_id'), (Bank, 'created_by'), (ExamClass, 'instructor_id'),
        (ExamGroup, 'instructor_id'), (Learning, 'autor_id'),
    ])
    if owns_content:
        flash(f'No se puede eliminar a "{user.username}": tiene exámenes, bancos, clases o capacitaciones. '
              'Cambia su contraseña para bloquear el acceso (ver Manual de administrador).', 'warning')
        return redirect(url_for('admin.dashboard'))

    db.session.delete(user)
    db.session.commit()
    flash(f'Cuenta del profesor "{user.username}" eliminada correctamente.', 'success')
    return redirect(url_for('admin.dashboard'))
