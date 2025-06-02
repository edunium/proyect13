from datetime import datetime, timezone, UTC # Use UTC for Python 3.12+
import random
from faker import Faker

# Importa la app y db de tu aplicación principal
from app import app, db, User, Department, Record, RecordHistory, generate_password_hash, DEPARTMENT_CODES

fake = Faker('es_ES') # Para generar datos en español

def seed_database():
    """
    Limpia la base de datos existente, recrea las tablas y
    llena con datos ficticios: un usuario admin, departamentos
    por defecto y 15 expedientes aleatorios.
    """
    with app.app_context(): # Esencial para operaciones de base de datos fuera de una ruta Flask
        print("Iniciando el proceso de seeding...")

        # 1. Blanquear la base de datos (eliminar todas las tablas)
        print("Eliminando todas las tablas existentes...")
        db.drop_all()
        print("Tablas eliminadas.")

        # 2. Recrear las tablas según los modelos definidos
        print("Creando nuevas tablas...")
        db.create_all()
        print("Tablas creadas.")

        # 3. Crear usuario administrador
        admin_dept_name = 'Administración' # Nombre del departamento para el admin
        
        # Asegurar que el departamento del admin exista
        admin_department_obj = Department.query.filter_by(name=admin_dept_name).first()
        if not admin_department_obj:
            admin_department_obj = Department(name=admin_dept_name, description='Tareas administrativas y gestión de usuarios.')
            db.session.add(admin_department_obj)
            db.session.commit() 
            print(f"Departamento '{admin_dept_name}' creado (ID: {admin_department_obj.id}).")
        else:
            # Esto no debería ocurrir si db.drop_all() funcionó
            print(f"Departamento '{admin_dept_name}' ya existía (ID: {admin_department_obj.id}).")


        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                password=generate_password_hash('admin'), 
                name='Administrador del Sistema',
                role='admin',
                department=admin_dept_name 
            )
            db.session.add(admin_user)
            db.session.commit() 
            print(f"Usuario administrador '{admin_user.username}' creado (ID: {admin_user.id}).")
        else:
            # Esto no debería ocurrir si db.drop_all() funcionó
            print(f"Usuario administrador '{admin_user.username}' ya existía (ID: {admin_user.id}).")
        
        admin_user_id = admin_user.id
        if not admin_user_id:
            print("Error crítico: No se pudo obtener el ID del usuario administrador. Saliendo.")
            return

        # 4. Crear departamentos por defecto
        default_departments_data = [
            {'name': 'Mesa de Entrada', 'description': 'Recepción y procesamiento inicial de expedientes.'},
            {'name': 'Intendencia', 'description': 'Oficina del intendente municipal.'},
            {'name': 'Obras Públicas', 'description': 'Gestión de obras y servicios públicos.'},
            {'name': 'Cultura', 'description': 'Gestión de actividades culturales.'},
            {'name': 'Cementerio', 'description': 'Administración y gestión del cementerio municipal.'},
            {'name': 'Hacienda', 'description': 'Gestión de finanzas y tributos municipales.'},
            {'name': 'Gobierno', 'description': 'Asuntos generales de gobierno y coordinación.'},
            {'name': 'Prensa', 'description': 'Comunicación y difusión institucional.'}
        ]
        
        print(f"Creando {len(default_departments_data)} departamentos por defecto...")
        created_default_departments_count = 0
        for dept_data in default_departments_data:
            dept = Department.query.filter_by(name=dept_data['name']).first()
            if not dept:
                dept = Department(name=dept_data['name'], description=dept_data['description'])
                db.session.add(dept)
                created_default_departments_count += 1
        
        if created_default_departments_count > 0:
            db.session.commit() 
            print(f"{created_default_departments_count} departamentos por defecto nuevos fueron añadidos y comiteados.")
        else:
            print("No se crearon nuevos departamentos por defecto (posiblemente ya existían, lo cual es inesperado después de drop_all).")


        all_departments_query = Department.query
        print(f"Total de departamentos en la BD después de la creación: {all_departments_query.count()}")
        if all_departments_query.count() > 0:
            for dept_obj in all_departments_query.all():
                print(f"  - Departamento en BD: ID: {dept_obj.id}, Nombre: {dept_obj.name}")
        
        # Exclude 'Administration' department from being assigned to general records, if other departments exist
        departments_for_records = Department.query.filter(Department.name != admin_dept_name).all()
        if not departments_for_records:
            print(f"Advertencia: No hay departamentos disponibles (excluyendo '{admin_dept_name}') para asignar a los expedientes. Se usarán todos los departamentos, incluyendo '{admin_dept_name}'.")
            departments_for_records = Department.query.all() # Fallback
        
        if not departments_for_records:
            print("Error crítico: No hay departamentos (ni siquiera con fallback) disponibles para asignar a los expedientes. Saliendo.")
            return
        
        print(f"Departamentos disponibles para la asignación de expedientes ficticios (count: {len(departments_for_records)}):")
        for dept_obj in departments_for_records:
            print(f"  - ID: {dept_obj.id}, Nombre: {dept_obj.name}")


        # 5. Crear 15 registros (expedientes) ficticios
        print(f"Iniciando creación de 15 expedientes ficticios asignados al usuario ID: {admin_user_id}...")
        records_created_count = 0
        for i in range(15):
            print(f"  Iteración {i+1}/15 para crear expediente:")
            if not departments_for_records: # Check the correct list
                print("    Error: la lista departments_for_records está vacía dentro del bucle. Saliendo del bucle.")
                break
            
            selected_department = random.choice(departments_for_records) # Use the filtered list
            print(f"    Departamento seleccionado: {selected_department.name} (ID: {selected_department.id})")
            
            # Get the last record number (globally) for sequence
            last_global_record = Record.query.order_by(Record.sequence_number.desc()).first()
            current_max_sequence = last_global_record.sequence_number if last_global_record else 0
            sequence_number = current_max_sequence + 1
            # Apply skipping logic for numbers ending in 8 or 9
            while sequence_number % 10 == 8 or sequence_number % 10 == 9:
                sequence_number += 1
            print(f"    Número de secuencia calculado (después de omitir 8/9): {sequence_number}")

            # Generate digital number (format: DEPT-SEQ-DD-MM-YYYY)
            dept_code = DEPARTMENT_CODES.get(selected_department.name, f"DPT{selected_department.id}")
            # Use current date for the number part, similar to add_record logic
            date_for_digital_number_str = datetime.now(UTC).strftime('%d-%m-%Y')
            digital_number = f"{dept_code}-{sequence_number:04d}-{date_for_digital_number_str}"
            print(f"    Número digital generado: {digital_number}")

            applicant_full_name = fake.name()
            applicant_dni = fake.unique.random_number(digits=8, fix_len=True)
            applicant_address = fake.address()
            applicant_phone = fake.phone_number()
            applicant_email = fake.email()

            # For the record's created_at field, we can use a faked past date for realism in seeding
            record_created_at_timestamp = fake.date_time_between(start_date='-1y', end_date='now', tzinfo=UTC) # Or timezone.utc

            # Generate a fake transaction date (can be None sometimes)
            transaction_date_for_seed = fake.date_time_between(start_date='-2y', end_date='-1d', tzinfo=UTC) if random.choice([True, False]) else None

            record = Record(
                sequence_number=sequence_number,
                digital_number=digital_number,
                full_name=applicant_full_name,
                dni=str(applicant_dni),
                address=applicant_address,
                phone=applicant_phone,
                email=applicant_email,
                description=fake.paragraph(nb_sentences=random.randint(2, 5)),
                transaction_date=transaction_date_for_seed,
                status=random.choice(['pending', 'urgente']), # Updated to new primary statuses
                department_id=selected_department.id,
                created_by=admin_user_id,
                created_at=record_created_at_timestamp,
                updated_at=record_created_at_timestamp, # Or datetime.now(UTC) if updated_at should be current
                attachment_filename=None,
                generated_pdf_filename=None # New field
            )
            db.session.add(record)
            try:
                db.session.flush() # Para obtener record.id para la entrada de historial
                
                # Crear entrada de historial para la creación
                history_entry = RecordHistory(
                    record_id=record.id,
                    user_id=admin_user_id, # Creado por el admin en el seeder
                    action_type="CREACIÓN",
                    details=f"Expediente iniciado en el departamento {selected_department.name}."
                )
                db.session.add(history_entry)
                db.session.commit()
                records_created_count += 1
                print(f"    Expediente ficticio '{digital_number}' creado y comiteado para {selected_department.name}.")
            except Exception as e:
                print(f"    ERROR al comitear el expediente {digital_number}: {e}")
                db.session.rollback() # Revertir en caso de error en este commit específico
                print(f"    Rollback realizado para el expediente {digital_number}.")
                # Considerar si continuar con el siguiente o detenerse
                # break # Descomentar si quieres detener el bucle en el primer error

        print(f"Total de {records_created_count} expedientes ficticios creados.")
        if records_created_count < 15:
            print("ADVERTENCIA: No se crearon los 15 expedientes esperados.")
        
        print("Proceso de seeding completado.")

if __name__ == '__main__':
    seed_database()
