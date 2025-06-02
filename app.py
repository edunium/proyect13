from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user # type: ignore
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from weasyprint import HTML, CSS # For PDF generation
import json # Added for passing data to template
from datetime import datetime, timezone, UTC # Python 3.12+ for UTC, otherwise use timezone.utc
#edunium
app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey' # type: ignore

# Standardized datetime format for the application
APP_WIDE_DATETIME_FORMAT = '%d/%m/%Y %H:%M'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///municipal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
from sqlalchemy import desc, or_ # Import 'or_' for complex queries
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Configuration for file uploads
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
GENERATED_PDF_FOLDER = 'generated_pdfs' # Folder for storing generated PDFs
app.config['GENERATED_PDF_FOLDER'] = GENERATED_PDF_FOLDER

# Special department name
MESA_DE_ENTRADA_DEPT_NAME = 'Mesa de Entrada' # Example, ensure it matches DB
INTENDENCIA_DEPT_NAME = 'Intendencia'         # Example, ensure it matches DB
PRIVILEGED_VIEW_DEPARTMENTS = [MESA_DE_ENTRADA_DEPT_NAME, INTENDENCIA_DEPT_NAME]

DEPARTMENT_CODES = {
    'Intendencia': 'IN',
    'Mesa de Entrada': 'ME',
    'Cultura': 'CU',
    'Cementerio': 'CE',
    'Obras Públicas': 'OP',
    'Hacienda': 'HA',
    'Administración': 'AD', # Changed from Administration
    'Gobierno': 'GO',
    'Prensa': 'PR'
}

# Allowed statuses for records - Ensure this list is comprehensive
ALLOWED_RECORD_STATUSES = ['activo', 'pendiente', 'en progreso', 'urgente']

# Inject current time into all templates
@app.context_processor
def inject_now():
    return {'now': datetime.now(UTC)} # Or datetime.now(timezone.utc) for older Python

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) # type: ignore
    name = db.Column(db.String(100))
    role = db.Column(db.String(20), default='user')
    department = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    history_actions = db.relationship('RecordHistory', backref='user', lazy='dynamic') # Para ver qué acciones hizo un usuario

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    records = db.relationship('Record', backref='department', lazy=True) # type: ignore

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('record.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    author = db.relationship('User', backref=db.backref('notes_authored', lazy='dynamic'))
    # The backref to Record will be 'record_associated' as defined in Record model

    def __repr__(self):
        return f'<Note {self.id} for Record {self.record_id} by User {self.user_id}>'

class RecordHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('record.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Quién realizó la acción
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(UTC), nullable=False)
    action_type = db.Column(db.String(50), nullable=False) # Ej: "Creación", "Modificación", "Reenvío", "Adjunto"
    details = db.Column(db.Text, nullable=True) # Descripción detallada de la acción

    def __repr__(self):
        return f'<RecordHistory {self.id} - {self.action_type} for Record {self.record_id}>'

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sequence_number = db.Column(db.Integer, nullable=False)
    digital_number = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(200), nullable=False) # Antes 'title'
    dni = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    transaction_date = db.Column(db.DateTime, nullable=True) # New field for transaction date
    email = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text)
    attachment_filename = db.Column(db.String(255), nullable=True) # New field for attachment
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    generated_pdf_filename = db.Column(db.String(255), nullable=True) # Stores the filename of the generated PDF
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_records') # Renombrado para evitar conflicto con User.history_actions
    
    # Relationship to get history entries for a record, ordered by most recent first
    history_entries = db.relationship('RecordHistory', 
                                      foreign_keys=[RecordHistory.record_id], # Explicit FK
                                      backref='record', 
                                      lazy='dynamic', 
                                      order_by=lambda: desc(RecordHistory.timestamp)) # Use lambda for late binding

    notes = db.relationship('Note',
                            foreign_keys=[Note.record_id],
                            backref='record_associated', # Allows note.record_associated
                            lazy='dynamic',
                            order_by=lambda: desc(Note.created_at)) # Use lambda for late binding

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper function to get the next available sequence number, skipping those ending in 8 or 9
def get_next_available_sequence_number():
    """Calculates the next available sequence number, skipping numbers ending in 8 or 9."""
    last_record = Record.query.order_by(Record.sequence_number.desc()).first()
    current_max_sequence = last_record.sequence_number if last_record else 0
    next_sequence = current_max_sequence + 1
    while next_sequence % 10 == 8 or next_sequence % 10 == 9:
        next_sequence += 1
    return next_sequence

# Create database and admin user
#@app.before_first_request
def create_tables_and_admin():
    db.create_all()

    # Ensure 'Administration' department exists for the admin user
    admin_dept_name = 'Administración' # Changed from Administration
    admin_department_obj = Department.query.filter_by(name=admin_dept_name).first()
    if not admin_department_obj:
        admin_department_obj = Department(name=admin_dept_name, description='Tareas administrativas y gestión de usuarios.')
        db.session.add(admin_department_obj)
        # Commit separately or ensure it's committed before admin user creation if it relies on ID.
        # For now, we'll commit at the end.

    # Check if admin user exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin_user = User(
            username='admin',
            password=generate_password_hash('admin'),
            name='Administrador',
            role='admin',
            department=admin_dept_name # Assign by name
        )
        db.session.add(admin_user)

        # Create default departments
        departments = [
            Department(name='Mesa de Entrada', description='Recepción y procesamiento inicial de expedientes'),
            Department(name='Intendencia', description='Oficina del intendente municipal'),
            Department(name='Obras Públicas', description='Gestión de obras y servicios públicos'),
            Department(name='Cultura', description='Gestión de actividades culturales.'),
            Department(name='Cementerio', description='Administración y gestión del cementerio municipal.'),
            Department(name='Hacienda', description='Gestión de finanzas y tributos municipales.'),
            Department(name='Gobierno', description='Asuntos generales de gobierno y coordinación.'),
            Department(name='Prensa', description='Comunicación y difusión institucional.')
        ]

        for dept in departments:
            db.session.add(dept)
            
        db.session.commit()

# Helper function to ensure necessary folders exist
def ensure_folders_exist():
    upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    if not os.path.exists(upload_path):
        os.makedirs(upload_path)
        app.logger.info(f"Created upload folder: {upload_path}")
    pdf_gen_path = os.path.join(app.root_path, app.config['GENERATED_PDF_FOLDER'])
    if not os.path.exists(pdf_gen_path):
        os.makedirs(pdf_gen_path)
        app.logger.info(f"Created PDF generation folder: {pdf_gen_path}")

# Helper function to generate PDF for a record
def generate_record_pdf(record_obj):
    if not record_obj:
        app.logger.error("generate_record_pdf: No record object provided.")
        return None

    pdf_folder = os.path.join(app.root_path, app.config['GENERATED_PDF_FOLDER'])
    # Ensure folder exists (should be handled at startup, but good to double check)
    if not os.path.exists(pdf_folder):
        os.makedirs(pdf_folder)

    pdf_filename = f"expediente_{record_obj.id}_{record_obj.digital_number.replace('-', '_')}.pdf"
    pdf_path = os.path.join(pdf_folder, pdf_filename)

    try:
        with app.test_request_context(base_url=request.url_root if request else 'http://localhost'): # Provides a basic request context
            html_string = render_template(
                'expediente_imprimir.html',
                record=record_obj,
                DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT,
                fecha_actual=datetime.now(UTC).strftime(APP_WIDE_DATETIME_FORMAT)
            )

        css_file_path = os.path.join(app.root_path, 'static', 'css', 'estilo_impresion.css')
        stylesheets = []
        if os.path.exists(css_file_path):
            stylesheets.append(CSS(filename=css_file_path))
        else:
            app.logger.warning(f"CSS file for PDF generation not found: {css_file_path}")

        html_to_render = HTML(string=html_string, base_url=request.url_root if request else app.config.get("APPLICATION_ROOT") or 'http://localhost/')
        html_to_render.write_pdf(pdf_path, stylesheets=stylesheets)

        record_obj.generated_pdf_filename = pdf_filename # Update the attribute on the object
        app.logger.info(f"Generated PDF for record {record_obj.id}: {pdf_filename}")
        return pdf_filename
    except Exception as e:
        app.logger.error(f"Error generating PDF for record {record_obj.id}: {e}", exc_info=True)
        return None
# Routes
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    is_admin = current_user.role == 'admin'
    # Verificar si el usuario actual pertenece al departamento de Intendencia
    is_intendencia_user = current_user.department == INTENDENCIA_DEPT_NAME

    if is_admin or is_intendencia_user:
        # El administrador o un usuario de Intendencia pueden ver todos los departamentos
        departments_for_dashboard = Department.query.order_by(Department.name).all()
        recent_records_list = Record.query.order_by(Record.created_at.desc()).limit(8).all()
    else:
        # Otros usuarios solo ven su propio departamento
        user_dept_name = current_user.department
        user_department_obj_for_dashboard = Department.query.filter_by(name=user_dept_name).first()
        
        if user_department_obj_for_dashboard:
            departments_for_dashboard = [user_department_obj_for_dashboard]
            recent_records_list = Record.query.filter_by(department_id=user_department_obj_for_dashboard.id)\
                                          .order_by(Record.created_at.desc()).limit(8).all()
        else:
            # Caso en que el departamento del usuario no se encuentra (debería ser raro)
            departments_for_dashboard = []
            recent_records_list = []
            flash(f"No se pudo encontrar su departamento asignado: '{user_dept_name}'. Por favor, contacte al administrador.", "warning")

    return render_template('dashboard.html', 
                           departments=departments_for_dashboard, 
                           recent_records=recent_records_list, 
                           DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT)

@app.route('/users')
@login_required
def users():
    if current_user.role != 'admin':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('dashboard'))
        
    users = User.query.all()
    return render_template('users.html', users=users, DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT)

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('dashboard'))
        
    departments = Department.query.all()
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        role = request.form.get('role')
        department = request.form.get('department')
        
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('El nombre de usuario ya existe', 'danger')
            return render_template('add_user.html', departments=departments)
            
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            name=name,
            role=role,
            department=department
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Usuario creado exitosamente', 'success')
        return redirect(url_for('users'))
        
    return render_template('add_user.html', departments=departments)

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    # Ensure only admin can access this route
    if current_user.role != 'admin':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('dashboard'))

    user_to_edit = User.query.get_or_404(user_id)
    departments = Department.query.all()

    # Prevent admin from editing their own role or deleting themselves via edit form (though delete route handles deletion)
    # For simplicity, we'll allow admin to edit their own name/department, but not role here.
    # A more robust system might have a separate "My Profile" page.

    if request.method == 'POST':
        # Get updated data from the form
        user_to_edit.username = request.form.get('username')
        user_to_edit.name = request.form.get('name')
        user_to_edit.department = request.form.get('department')
        
        # Only allow changing role if the user being edited is NOT the admin
        if user_to_edit.username != 'admin':
             user_to_edit.role = request.form.get('role')

        # Handle password change only if a new password is provided
        new_password = request.form.get('password')
        if new_password:
            user_to_edit.password = generate_password_hash(new_password)

        try:
            db.session.commit()
            flash(f'Usuario "{user_to_edit.username}" actualizado exitosamente', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el usuario: {e}', 'danger')
            # Re-render the form with current data and errors
            return render_template('edit_user.html', user=user_to_edit, departments=departments)

    # GET request: Render the edit form
    return render_template('edit_user.html', user=user_to_edit, departments=departments)

# Note: Using GET for delete is simpler with the current template's <a> tags,
# but POST is generally recommended for destructive actions.
@app.route('/users/delete/<int:user_id>', methods=['GET']) # Changed to GET to match template <a> tag
@login_required
def delete_user(user_id):
    # Ensure only admin can access this route
    if current_user.role != 'admin':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('dashboard'))

    user_to_delete = User.query.get_or_404(user_id)

    if user_to_delete.username == 'admin':
        flash('No puedes eliminar al usuario administrador principal.', 'danger')
    else:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'Usuario "{user_to_delete.username}" eliminado exitosamente', 'success')

    return redirect(url_for('users'))

@app.route('/records')
@login_required
def records():
    department_id_from_arg = request.args.get('department', default=None, type=int)
    search_term = request.args.get('search_term', default=None, type=str)
    status_filter = request.args.get('status', default=None, type=str)

    query = Record.query.join(Department, Record.department_id == Department.id)\
                        .join(User, Record.created_by == User.id)

    is_admin = current_user.role == 'admin'
    is_privileged_viewer = current_user.department in PRIVILEGED_VIEW_DEPARTMENTS
    can_view_all_initial = is_admin or is_privileged_viewer

    effective_department_id_filter = None
    departments_for_dropdown = []
    page_header_department_obj = None

    if can_view_all_initial:
        departments_for_dropdown = Department.query.order_by(Department.name).all()
        if department_id_from_arg:
            query = query.filter(Record.department_id == department_id_from_arg)
            effective_department_id_filter = department_id_from_arg
            page_header_department_obj = Department.query.get(department_id_from_arg)
        # If no department_id_from_arg, query remains unfiltered by department for these users
    else: # Regular user, restricted to their department
        user_dept_name = current_user.department
        user_dept_obj = Department.query.filter_by(name=user_dept_name).first()
        if user_dept_obj:
            query = query.filter(Record.department_id == user_dept_obj.id)
            effective_department_id_filter = user_dept_obj.id
            departments_for_dropdown = [user_dept_obj]
            page_header_department_obj = user_dept_obj
        else: # User's department not found
            query = query.filter(db.false()) # Show no records
            # departments_for_dropdown remains empty
            # page_header_department_obj remains None

    if status_filter:
        query = query.filter(Record.status == status_filter)

    if search_term and search_term.strip():
        search_term_cleaned = search_term.strip()
        search_pattern = f"%{search_term_cleaned}%"
        query = query.filter(or_(
            Record.digital_number.ilike(search_pattern),
            Record.full_name.ilike(search_pattern),
            Record.description.ilike(search_pattern),
            Department.name.ilike(search_pattern)
        ))

    records_list = query.order_by(Record.created_at.desc()).all()

    return render_template('records.html', 
                           records=records_list, 
                           departments=departments_for_dropdown,
                           selected_department_id=effective_department_id_filter,
                           department=page_header_department_obj,
                           search_term=search_term, # Keep this for the input field value
                           selected_status=status_filter, DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT)

@app.route('/records/add', methods=['GET', 'POST'])
@login_required
def add_record():
    is_admin = current_user.role == 'admin'
    # For adding records, Mesa de Entrada users are restricted to their own department.
    # Only admins can select any department.
    user_can_select_any_department = is_admin

    departments_for_select_dropdown = []
    user_department_for_form = None # The user's department object if they are restricted

    if user_can_select_any_department: # Admin
        departments_for_select_dropdown = Department.query.order_by(Department.name).all()
    else: # Regular user or Mesa de Entrada user
        user_dept_name = current_user.department
        user_department_obj = Department.query.filter_by(name=user_dept_name).first()
        if user_department_obj:
            departments_for_select_dropdown = [user_department_obj]
            user_department_for_form = user_department_obj
        else:
            flash(f"No se pudo encontrar tu departamento asignado ({user_dept_name}) para crear el expediente.", "danger")
            return redirect(url_for('dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        # ... (other form gets)

        # Helper function or inline logic for re-render parameters
        def get_params_for_rerender(current_form_data):
            last_rec = Record.query.order_by(Record.sequence_number.desc()).first()
            raw_next_seq = (last_rec.sequence_number + 1) if last_rec else 1
            next_seq = get_next_available_sequence_number()
            current_date_str_for_num_gen = datetime.now(UTC).strftime('%d-%m-%Y') # For digital number generation
            default_transaction_date_val = current_form_data.get('transaction_date') or datetime.now(UTC).strftime('%Y-%m-%dT%H:%M') # Format for datetime-local
            dept_codes_json = json.dumps(DEPARTMENT_CODES)
            return {
                "departments": departments_for_select_dropdown,
                "user_department": user_department_for_form,
                "current_data": current_form_data,
                "default_transaction_date_str": default_transaction_date_val, # For the input value
                "next_sequence_number": next_seq,
                "raw_next_sequence_number": raw_next_seq,
                "current_date_str_for_number": current_date_str_for_num_gen, # For the digital number suggestion
                "department_codes_json": dept_codes_json
            }

        dni = request.form.get('dni')
        address = request.form.get('address')
        phone = request.form.get('phone')
        email = request.form.get('email')
        description = request.form.get('description')
        status_from_form = request.form.get('status') # Leer el nuevo campo 'status'
        transaction_date_str = request.form.get('transaction_date')
        department_id = request.form.get('department_id', type=int)
        attachment_file = request.files.get('attachment')
        manual_sequence_number_str = request.form.get('manual_sequence_number', '').strip()
        
        # Validate department selection and authorization
        if not department_id:
            flash('Debe seleccionar un departamento.', 'danger')
            return render_template('add_record.html', **get_params_for_rerender(request.form))

        selected_department_obj = Department.query.get(department_id)
        if not selected_department_obj:
            flash('Departamento no válido.', 'danger')
            return render_template('add_record.html', **get_params_for_rerender(request.form))

        if not user_can_select_any_department: # User is restricted (not admin)
            # Their selected department must be their own department
            if not user_department_for_form or selected_department_obj.id != user_department_for_form.id:
                flash('No tiene permisos para crear expedientes en el departamento seleccionado.', 'danger')
                return render_template('add_record.html', **get_params_for_rerender(request.form))

        sequence_number_to_use = None

        if manual_sequence_number_str:
            try:
                manual_seq_int = int(manual_sequence_number_str)
                if not (0 < manual_seq_int < 10000): # Basic validation for 4 digits, adjust as needed
                    raise ValueError("Sequence number out of typical range.")
                
                # Check if this manually entered sequence number is already taken
                existing_record_by_seq = Record.query.filter_by(sequence_number=manual_seq_int).first()
                if existing_record_by_seq:
                    flash(f'El número de secuencia manual "{manual_seq_int:04d}" ya está en uso.', 'danger')
                    return render_template('add_record.html', **get_params_for_rerender(request.form))
                sequence_number_to_use = manual_seq_int
            except ValueError:
                flash('El número de secuencia manual debe ser un número válido (ej: 0008).', 'danger')
                return render_template('add_record.html', **get_params_for_rerender(request.form))
        else:
            # Get the next available sequence number using the helper function (skips 8 and 9)
            sequence_number_to_use = get_next_available_sequence_number()

        # Generate digital number (format: DEPT-SEQ-DD-MM-YYYY)
        dept_code = DEPARTMENT_CODES.get(selected_department_obj.name, f"DPT{selected_department_obj.id}")
        date_str_for_number = datetime.now(UTC).strftime('%d-%m-%Y') # Format: DD-MM-YYYY
        digital_number = f"{dept_code}-{sequence_number_to_use:04d}-{date_str_for_number}"
        
        attachment_savename = None
        if attachment_file and attachment_file.filename != '':
            original_filename_secure = secure_filename(attachment_file.filename)
            _ , ext_part = os.path.splitext(original_filename_secure)
            current_date_str = datetime.now(UTC).strftime('%d-%m-%Y')
            solicitante_name_part = secure_filename(full_name.replace(" ", "_").lower()) # Usar full_name para el nombre
            
            # Construct the new filename: DEPT_CODE-SEQ_NUM-SOLICITANTE_NAME-DATE.EXT
            # Example: OP-0001-juan_perez-23-10-2023.pdf
            new_filename = f"{dept_code}-{sequence_number_to_use:04d}-{solicitante_name_part}-{current_date_str}{ext_part}"
            
            # Ensure UPLOAD_FOLDER path is absolute or correctly relative for os.path.join
            upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
            attachment_file.save(os.path.join(upload_path, new_filename))
            attachment_savename = new_filename
        
        # Process transaction_date
        transaction_datetime = None
        if transaction_date_str:
            try:
                # Format from datetime-local input is 'YYYY-MM-DDTHH:MM'
                transaction_datetime = datetime.strptime(transaction_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=UTC)
            except ValueError:
                flash('Fecha de trámite no válida. Asegúrese de que el formato sea correcto y la fecha/hora existan.', 'danger')
                return render_template('add_record.html', **get_params_for_rerender(request.form))

        new_record = Record(
            sequence_number=sequence_number_to_use,
            digital_number=digital_number,
            full_name=full_name,
            dni=dni,
            address=address,
            phone=phone,
            email=email,
            transaction_date=transaction_datetime,
            description=description,
            department_id=selected_department_obj.id,
            attachment_filename=attachment_savename,
            created_by=current_user.id,
            status=status_from_form # Asignar el valor del formulario al campo status del Record
        )
        
        db.session.add(new_record)
        db.session.flush() # Flush to get new_record.id

        # Log history
        history_entry = RecordHistory(
            record_id=new_record.id,
            user_id=current_user.id, # type: ignore
            action_type="CREACIÓN",
            details=f"Expediente iniciado en el departamento {selected_department_obj.name}."
        )
        db.session.add(history_entry)

        # Generate PDF for the new record
        # The new_record object is already in session and has its ID after flush.
        # generate_record_pdf will modify its generated_pdf_filename attribute.
        generated_pdf_file = generate_record_pdf(new_record)
        if not generated_pdf_file:
            flash('Expediente creado, pero hubo un error al generar el PDF asociado.', 'warning')
        
        # Commit everything: record, history, and pdf filename (if set)
        db.session.commit()

        flash('Expediente creado exitosamente', 'success')
        return redirect(url_for('records', department=selected_department_obj.id))
    
    # GET request:
    # For suggested number display
    last_record_for_raw_get = Record.query.order_by(Record.sequence_number.desc()).first()
    raw_next_sequence_number_get = (last_record_for_raw_get.sequence_number + 1) if last_record_for_raw_get else 1
    
    next_sequence_number = get_next_available_sequence_number()
    current_date_str_for_number = datetime.now(UTC).strftime('%d-%m-%Y')
    department_codes_json = json.dumps(DEPARTMENT_CODES)
    default_transaction_date_str_get = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M') # Format for datetime-local

    return render_template('add_record.html', departments=departments_for_select_dropdown, 
                           user_department=user_department_for_form, current_data={},
                           next_sequence_number=next_sequence_number,
                           raw_next_sequence_number=raw_next_sequence_number_get,
                           current_date_str_for_number=current_date_str_for_number,
                           department_codes_json=department_codes_json,
                           default_transaction_date_str=default_transaction_date_str_get # For the input value
                           )

@app.route('/records/<int:record_id>')
@login_required
def view_record(record_id):
    record = Record.query.get_or_404(record_id)

    is_admin = current_user.role == 'admin'
    is_privileged_viewer = current_user.department in PRIVILEGED_VIEW_DEPARTMENTS
    
    can_view_this_record = is_admin or is_privileged_viewer or (record.department.name == current_user.department)

    if not can_view_this_record:
        flash('No tiene permisos para ver este expediente.', 'danger')
        return redirect(url_for('dashboard')) 
        
    # For the "Resend" feature, pass all departments and the Intendencia department name
    all_departments_for_dropdown = Department.query.order_by(Department.name).all()
        
    return render_template('view_record.html', record=record, 
                           DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT,
                           INTENDENCIA_DEPT_NAME=INTENDENCIA_DEPT_NAME,
                           all_departments=all_departments_for_dropdown)

@app.route('/records/<int:record_id>/print_view') # edunius
@login_required
def print_record_view(record_id):
    record = Record.query.get_or_404(record_id)

    # Permisos: Cualquier usuario que pueda ver el expediente, puede imprimirlo.
    # Esta lógica es similar a la de la ruta view_record.
    is_admin = current_user.role == 'admin'
    is_privileged_viewer = current_user.department in PRIVILEGED_VIEW_DEPARTMENTS
    
    can_access_this_record = is_admin or is_privileged_viewer or (record.department.name == current_user.department)

    if not can_access_this_record:
        flash('No tiene permisos para imprimir este expediente.', 'danger')
        # Redirigir a la vista del expediente o al dashboard según prefieras
        return redirect(url_for('view_record', record_id=record.id)) 
        
    return render_template('expediente_imprimir.html', 
                           record=record,
                           fecha_actual=datetime.now(UTC).strftime(APP_WIDE_DATETIME_FORMAT), # Changed from H:M:S to H:M
                           DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT)



@app.route('/records/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    if current_user.role != 'admin':
        flash('Acceso no autorizado. Solo los administradores pueden editar expedientes.', 'danger')
        return redirect(url_for('records'))

    record_to_edit = Record.query.get_or_404(record_id)
    departments_for_select = Department.query.order_by(Department.name).all()

    if request.method == 'POST':
        changed_fields_details = [] # To build a more detailed history message
        made_any_change = False # Flag to track if any field was actually changed

        try:
            original_status_for_history = record_to_edit.status # For history comparison
            # Basic fields
            original_department_id = record_to_edit.department_id
            record_to_edit.full_name = request.form.get('full_name', record_to_edit.full_name)
            record_to_edit.dni = request.form.get('dni', record_to_edit.dni)
            record_to_edit.address = request.form.get('address', record_to_edit.address)
            record_to_edit.phone = request.form.get('phone', record_to_edit.phone)
            record_to_edit.email = request.form.get('email', record_to_edit.email)
            record_to_edit.description = request.form.get('description', record_to_edit.description)

            # Transaction Date
            transaction_date_str = request.form.get('transaction_date')
            if transaction_date_str:
                # Format from datetime-local input is 'YYYY-MM-DDTHH:MM'
                record_to_edit.transaction_date = datetime.strptime(transaction_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=UTC)
            else:
                record_to_edit.transaction_date = None # Allow clearing the date

            # Department Change and Digital Number Regeneration
            new_department_id = request.form.get('department_id', type=int)
            department_changed_and_status_updated = False # Flag for conditional flashing
            original_department_name_for_flash = ""
            new_department_obj_for_flash = None

            if new_department_id and new_department_id != original_department_id:
                # Capture the current department name BEFORE changing it, for the flash message
                original_department_name_for_flash = record_to_edit.department.name

                new_department_obj = Department.query.get(new_department_id)
                new_department_obj_for_flash = new_department_obj # Store for later flash
                if new_department_obj:
                    record_to_edit.department_id = new_department_id
                    # Regenerate digital_number: Keep sequence, update dept code and date of change
                    new_dept_code = DEPARTMENT_CODES.get(new_department_obj.name, f"DPT{new_department_obj.id}")
                    date_str_for_number = datetime.now(UTC).strftime('%d-%m-%Y') # Date of this significant change
                    record_to_edit.digital_number = f"{new_dept_code}-{record_to_edit.sequence_number:04d}-{date_str_for_number}"
                    # Set status to 'pending' due to department change, admin can override this next.
                    if record_to_edit.status != 'pending':
                        record_to_edit.status = 'pending' 
                    department_changed_and_status_updated = True
                    made_any_change = True # Department change is a significant change
                else:
                    flash('Departamento seleccionado no válido.', 'danger')
                    # Pass current form data back to template for repopulation
                    return render_template('edit_record.html', record=record_to_edit, departments=departments_for_select, current_data=request.form, ALLOWED_RECORD_STATUSES=ALLOWED_RECORD_STATUSES, DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT)

            # Admin's explicit status choice (can override 'pending' from department change)
            if current_user.role == 'admin': # Route is admin-only
                selected_status_by_admin = request.form.get('status') # from the new <select>
                if selected_status_by_admin and selected_status_by_admin in ALLOWED_RECORD_STATUSES:
                    if record_to_edit.status != selected_status_by_admin:
                        record_to_edit.status = selected_status_by_admin
                        made_any_change = True # Status change is a significant change
                elif selected_status_by_admin and selected_status_by_admin not in ALLOWED_RECORD_STATUSES:
                    flash(f'El estado "{selected_status_by_admin}" seleccionado no es válido. El estado no fue cambiado por esta selección.', 'warning')

            if department_changed_and_status_updated: # If department was changed
                flash(f"El departamento fue cambiado de '{original_department_name_for_flash}' a '{new_department_obj_for_flash.name if new_department_obj_for_flash else 'N/A'}'. El estado se actualizó a '{record_to_edit.status.capitalize()}' y el número digital se regeneró.", "info")

            # Attachment Handling
            attachment_file = request.files.get('attachment')
            if attachment_file and attachment_file.filename != '':
                original_filename_secure = secure_filename(attachment_file.filename)
                _, ext_part = os.path.splitext(original_filename_secure)
                
                # Fetch the department object based on the record_to_edit.department_id (which might have just been updated)
                dept_for_filename_obj = Department.query.get(record_to_edit.department_id)
                if not dept_for_filename_obj:
                    flash("Error crítico: No se pudo determinar el departamento para el nombre del archivo.", "danger")
                    return redirect(url_for('view_record', record_id=record_to_edit.id)) # Or handle error more gracefully

                dept_code_for_filename = DEPARTMENT_CODES.get(dept_for_filename_obj.name, f"DPT{dept_for_filename_obj.id}")
                sequence_num_for_filename = record_to_edit.sequence_number
                solicitante_name_part = secure_filename(record_to_edit.full_name.replace(" ", "_").lower())
                current_date_str_for_filename = datetime.now(UTC).strftime('%d-%m-%Y') # Date of upload/change

                new_attachment_savename = f"{dept_code_for_filename}-{sequence_num_for_filename:04d}-{solicitante_name_part}-{current_date_str_for_filename}{ext_part}"
                
                upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
                
                # Remove old file if it exists and is different
                if record_to_edit.attachment_filename and record_to_edit.attachment_filename != new_attachment_savename:
                    old_file_path = os.path.join(upload_path, record_to_edit.attachment_filename)
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                        except OSError as e:
                            app.logger.warning(f"Could not delete old attachment {old_file_path}: {e}")
                            flash(f"Advertencia: No se pudo eliminar el adjunto anterior '{record_to_edit.attachment_filename}'.", "warning")

                attachment_file.save(os.path.join(upload_path, new_attachment_savename))
                record_to_edit.attachment_filename = new_attachment_savename
                made_any_change = True # Attachment change is a significant change
            
            # Check if any other basic field (not covered by specific flags like department or attachment) changed
            # This is a simplified check; a more robust way would compare each field individually.
            # For now, if made_any_change is True due to dept, status, or attachment, or if other fields were modified by request.form.get
            # we assume a change. A more precise check would be needed for a perfect "no changes" message.
            # The existing logic doesn't explicitly track changes for all basic fields for the 'made_any_change' flag.
            # We'll rely on the fact that if any of the specific handlers (dept, status, attachment) set made_any_change, it's true.
            # Or if the form submission itself implies changes.

            db.session.flush() # Ensure updated_at is set if it changed due to onupdate
            
            # Log history for modification
            history_entry = RecordHistory(
                record_id=record_to_edit.id,
                user_id=current_user.id, # type: ignore
                action_type="MODIFICACIÓN",
                details=f"Datos del expediente actualizados. Departamento final: {record_to_edit.department.name}. Estado final: {record_to_edit.status.capitalize()}."
            )
            db.session.add(history_entry)

            # Regenerate PDF after potential changes
            updated_pdf_file = generate_record_pdf(record_to_edit)
            if not updated_pdf_file:
                # Only flash if the main update was successful but PDF failed
                if not department_changed_and_status_updated:
                     flash('Expediente actualizado, pero hubo un error al regenerar el PDF asociado.', 'warning')
                else:
                     flash('Advertencia: Hubo un error al regenerar el PDF asociado tras la actualización.', 'warning')
            
            db.session.commit() # Commit all changes: record data, history, pdf filename

            # Show generic success if department didn't change (as it has its own flash) and PDF was fine.
            if not department_changed_and_status_updated and made_any_change and updated_pdf_file:
                flash('Expediente actualizado exitosamente!', 'success')
            return redirect(url_for('view_record', record_id=record_to_edit.id))

        except ValueError as ve: # Catch specific errors like invalid date format if not caught by browser
            db.session.rollback()
            flash(f'Error en los datos del formulario: {ve}', 'danger')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error al actualizar el expediente {record_id}: {e}", exc_info=True)
            flash(f'Error al actualizar el expediente: {str(e)}', 'danger')
        
        # If any error occurs and we don't redirect, re-render with current form data
        return render_template('edit_record.html', record=record_to_edit, departments=departments_for_select, current_data=request.form, ALLOWED_RECORD_STATUSES=ALLOWED_RECORD_STATUSES, DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT)

    # GET request: Render the edit form, passing None for current_data initially
    return render_template('edit_record.html', record=record_to_edit, departments=departments_for_select, current_data=None, ALLOWED_RECORD_STATUSES=ALLOWED_RECORD_STATUSES, DATETIME_APP_FORMAT=APP_WIDE_DATETIME_FORMAT)

@app.route('/records/<int:record_id>/attach', methods=['POST'])
@login_required
def attach_file_to_record(record_id):
    record = Record.query.get_or_404(record_id)

    is_admin = current_user.role == 'admin'
    is_privileged_viewer = current_user.department in PRIVILEGED_VIEW_DEPARTMENTS
    can_modify_this_record = is_admin or is_privileged_viewer or (record.department.name == current_user.department)

    if not can_modify_this_record:
        flash('No tiene permisos para adjuntar archivos a este expediente.', 'danger')
        return redirect(url_for('view_record', record_id=record.id))
    
    if 'attachment' not in request.files:
        flash('No se encontró el archivo en la solicitud.', 'danger')
        return redirect(url_for('view_record', record_id=record.id))
        
    file = request.files['attachment']
    
    if file.filename == '':
        flash('No se seleccionó ningún archivo para subir.', 'warning')
        return redirect(url_for('view_record', record_id=record.id))
        
    if file:
        original_filename_secure = secure_filename(file.filename)
        _ , ext_part = os.path.splitext(original_filename_secure) # Solo necesitamos la extensión
        current_date_str = datetime.now(UTC).strftime('%d-%m-%Y')
        
        # Get department code and sequence number from the existing record
        # Use defined department codes, fallback to DPT<ID> if not found
        dept_code = DEPARTMENT_CODES.get(record.department.name, f"DPT{record.department.id}")
        sequence_number = record.sequence_number # sequence_number is already part of the record
        solicitante_name_part = secure_filename(record.full_name.replace(" ", "_").lower()) # Usar record.full_name
        
        new_filename = f"{dept_code}-{sequence_number:04d}-{solicitante_name_part}-{current_date_str}{ext_part}"
        
        upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
        file.save(os.path.join(upload_path, new_filename))
        record.attachment_filename = new_filename # Store the new filename
        
        # Log history for attachment
        history_entry = RecordHistory(
            record_id=record.id,
            user_id=current_user.id, # type: ignore
            action_type="ADJUNTO",
            # We don't know if it's a replacement without checking old value, simplify for now
            details=f"Archivo '{new_filename}' fue adjuntado/actualizado." 
        )
        db.session.add(history_entry)
        db.session.commit()
        flash('Archivo adjuntado exitosamente.', 'success')

    return redirect(url_for('view_record', record_id=record.id))

@app.route('/uploads/<path:filename>')
@login_required
def download_file(filename):
    # This route is for general uploads. We'll add a new one for generated PDFs.
    upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    return send_from_directory(upload_path, filename, as_attachment=False) # as_attachment=False to display in browser if possible

@app.route('/generated_pdfs/<path:filename>')
@login_required
def download_generated_pdf(filename):
    upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    return send_from_directory(upload_path, filename, as_attachment=False)

@app.route('/records/<int:record_id>/resend', methods=['POST'])
@login_required
def resend_record(record_id):
    record_to_resend = Record.query.get_or_404(record_id)

    # Permission checks:
    # User must be (admin role AND in Intendencia department) OR the main superadmin (username 'admin')
    is_intendencia_admin = current_user.role == 'admin' and current_user.department == INTENDENCIA_DEPT_NAME # type: ignore
    if not (is_intendencia_admin or current_user.username == 'admin'):
        flash('No tiene permisos para realizar esta acción.', 'danger')
        return redirect(url_for('view_record', record_id=record_id))

    # Record must be in 'pending' or 'urgente' status
    if record_to_resend.status not in ['pending', 'urgente']:
        flash('Solo los expedientes en estado "pendiente" o "urgente" pueden ser re-enviados.', 'warning')
        return redirect(url_for('view_record', record_id=record_id))

    new_department_id = request.form.get('new_department_id', type=int)
    if not new_department_id:
        flash('Debe seleccionar un nuevo departamento de destino.', 'danger')
        return redirect(url_for('view_record', record_id=record_id))

    new_department_obj = Department.query.get(new_department_id)
    if not new_department_obj:
        flash('El departamento de destino seleccionado no es válido.', 'danger')
        return redirect(url_for('view_record', record_id=record_id))

    if new_department_obj.id == record_to_resend.department_id:
        flash(f'El expediente ya se encuentra en el departamento "{new_department_obj.name}". No se realizaron cambios.', 'info')
        return redirect(url_for('view_record', record_id=record_id))

    try:
        original_department_name = record_to_resend.department.name
        leaving_department_obj = record_to_resend.department # Department record is currently in (before update)

        # Store the digital number string as it is BEFORE any changes in this transaction.
        # This is the number we need to parse for the original date part.
        current_digital_number_on_record = record_to_resend.digital_number

        # Update department and status first
        record_to_resend.department_id = new_department_obj.id
        record_to_resend.status = 'in_progress' # Change status to "En Progreso"

        # Regenerate digital_number based on the new requirement:
        # Format: LEAVING_DEPT_CODE-ARRIVING_DEPT_CODE-SEQ_NUM-ORIGINAL_DATE_PART

        leaving_dept_code = DEPARTMENT_CODES.get(leaving_department_obj.name, f"DPT{leaving_department_obj.id}")
        arriving_dept_code = DEPARTMENT_CODES.get(new_department_obj.name, f"DPT{new_department_obj.id}")
        sequence_number_int = int(record_to_resend.sequence_number)

        current_dn_parts = current_digital_number_on_record.split('-')
        if len(current_dn_parts) < 5: # Expects at least DEPT-SEQ-DD-MM-YYYY (5 parts)
            app.logger.error(f"Digital number '{current_digital_number_on_record}' for record {record_to_resend.id} is too short to parse date and sequence.")
            flash(f"Error: Formato de número digital '{current_digital_number_on_record}' no es válido para extraer fecha y secuencia. No se pudo actualizar el número digital.", "danger")
            db.session.rollback() # Rollback department/status changes if number can't be formed correctly.
            return redirect(url_for('view_record', record_id=record_id))

        original_date_part_for_new_number = f"{current_dn_parts[-3]}-{current_dn_parts[-2]}-{current_dn_parts[-1]}"

        new_digital_number_value = f"{leaving_dept_code}-{arriving_dept_code}-{sequence_number_int:04d}-{original_date_part_for_new_number}"
        record_to_resend.digital_number = new_digital_number_value

        # Log history for resend
        history_detail = (f"Movido del departamento '{original_department_name}' al departamento '{new_department_obj.name}'. "
                          f"Nuevo número digital: {new_digital_number_value}. Estado actualizado a 'En Progreso'.")
        history_entry = RecordHistory(
            record_id=record_to_resend.id,
            user_id=current_user.id, # type: ignore
            action_type="REENVÍO",
            details=history_detail
        )
        db.session.add(history_entry)

        # Regenerate PDF after resend
        resent_pdf_file = generate_record_pdf(record_to_resend)
        if not resent_pdf_file:
            flash(f'Expediente re-enviado, pero hubo un error al regenerar el PDF asociado.', 'warning')

        # Commit all changes: record data, history, pdf filename
        # record.updated_at will be handled by onupdate in the model if not already set by other logic
        db.session.commit() 


        flash(f'Expediente (antes en {original_department_name}) re-enviado a "{new_department_obj.name}". Nuevo N°: {record_to_resend.digital_number}. Estado: En Progreso.', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al re-enviar el expediente {record_id}: {e}", exc_info=True)
        flash(f'Error al re-enviar el expediente: {str(e)}', 'danger')

    return redirect(url_for('view_record', record_id=record_id))

@app.route('/records/<int:record_id>/add_note', methods=['POST'])
@login_required
def add_note_to_record(record_id):
    record = Record.query.get_or_404(record_id)

    # Permission check: User must be able to view the record to add a note
    is_admin = current_user.role == 'admin'
    is_privileged_viewer = current_user.department in PRIVILEGED_VIEW_DEPARTMENTS
    can_interact_with_record = is_admin or is_privileged_viewer or (record.department.name == current_user.department)

    if not can_interact_with_record:
        flash('No tiene permisos para agregar notas a este expediente.', 'danger')
        return redirect(url_for('view_record', record_id=record.id))

    note_content = request.form.get('note_content')
    if not note_content or not note_content.strip():
        flash('El contenido de la nota no puede estar vacío.', 'warning')
        return redirect(url_for('view_record', record_id=record.id))

    new_note = Note(
        record_id=record.id,
        user_id=current_user.id, # type: ignore
        content=note_content.strip()
    )
    db.session.add(new_note)
    
    history_entry = RecordHistory(
        record_id=record.id,
        user_id=current_user.id, # type: ignore
        action_type="NOTA AGREGADA",
        details=f"Nota agregada por {current_user.name}: '{note_content[:100]}{'...' if len(note_content) > 100 else ''}'"
    )
    db.session.add(history_entry)
    db.session.commit()
    flash('Nota agregada exitosamente.', 'success')
    return redirect(url_for('view_record', record_id=record.id))

if __name__ == '__main__':
    # It's good practice to ensure tables are created.
    # The @app.before_first_request decorator is deprecated.
    # You can call this function within an app context before running the app.
    with app.app_context():
        create_tables_and_admin()
        ensure_folders_exist() # Ensure upload and PDF folders exist
    app.run(debug=True)
    








    