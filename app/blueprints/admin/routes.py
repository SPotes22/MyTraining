from functools import wraps
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.services import audit
from app.models import User, Exam, ExamSession, Bank, ExamClass, ExamGroup, Learning, AuditLog
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
    db.session.flush()
    audit.record('user.create', 'user', instructor.id, role='instructor')
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
    audit.record('user.delete', 'user', user.id, role=user.role)
    db.session.commit()
    flash(f'Cuenta del profesor "{user.username}" eliminada correctamente.', 'success')
    return redirect(url_for('admin.dashboard'))


AUDIT_PAGE_SIZE = 100


@admin_bp.route('/audit')
@login_required
@admin_required
def audit_log():
    """RF-030: consulta del registro de auditoría, del más reciente al más antiguo."""
    action = request.args.get('action', '').strip()
    user_id = request.args.get('user_id', type=int)
    page = max(request.args.get('page', type=int, default=1), 1)
    query = AuditLog.query
    if action:
        query = query.filter(AuditLog.action.like(f'{action}%'))
    if user_id:
        query = query.filter_by(user_id=user_id)
    total = query.count()
    logs = (query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * AUDIT_PAGE_SIZE).limit(AUDIT_PAGE_SIZE).all())
    users = {u.id: u for u in User.query.filter(User.id.in_({l.user_id for l in logs if l.user_id})).all()}
    actions = sorted({a for (a,) in db.session.query(AuditLog.action).distinct()})
    return render_template('admin_audit.html', logs=logs, users=users, actions=actions, action=action,
                           user_id=user_id, page=page, total=total, page_size=AUDIT_PAGE_SIZE)
