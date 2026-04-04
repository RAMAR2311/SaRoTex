import os
import pandas as pd
from io import BytesIO
from werkzeug.utils import secure_filename
from flask import current_app, Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Product, StockAdjustment
from decorators import admin_required

inventory_bp = Blueprint('inventory_bp', __name__)

@inventory_bp.route('/', methods=['GET'])
@login_required
@admin_required
def index():
    productos = Product.query.order_by(Product.nombre).all()
    return render_template('inventory/index.html', productos=productos)

@inventory_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo():
    if request.method == 'POST':
        # --- Manejo de Imagen ---
        imagen_filename = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                imagen_filename = filename

        # La instanciación agrupa todos los parámetros del nuevo producto
        nuevo_prod = Product(
            sku=request.form.get('sku').strip(),
            nombre=request.form.get('nombre').strip(),
            cantidad_stock=int(request.form.get('cantidad_stock', 0)),
            precio_costo=float(request.form.get('precio_costo', 0.0)),
            precio_minimo=float(request.form.get('precio_minimo', 0.0)),
            precio_sugerido=float(request.form.get('precio_sugerido', 0.0)),
            imagen=imagen_filename,
            observacion=request.form.get('observacion')
        )
        try:
            db.session.add(nuevo_prod)
            db.session.commit()
            
            # Crear ajuste inicial automáticamente en el Kardex
            ajuste_inicial = StockAdjustment(
                product_id=nuevo_prod.id,
                admin_id=current_user.id,
                tipo_movimiento='Creación Inicial',
                stock_anterior=0,
                stock_nuevo=nuevo_prod.cantidad_stock
            )
            db.session.add(ajuste_inicial)
            db.session.commit()

            flash('Producto creado exitosamente.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error al intentar guardar el producto en la base de datos.', 'danger')
            
    return render_template('inventory/form.html')

@inventory_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_producto(id):
    # get_or_404 protege la ruta en caso de que se envíe un ID inexistente en la URL
    producto = Product.query.get_or_404(id)
    
    if request.method == 'POST':
        stock_anterior = producto.cantidad_stock
        cantidad_stock_nueva = int(request.form.get('cantidad_stock', 0))
        
        # Actualizar Imagen si se sube una nueva
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                producto.imagen = filename
                
        # Se actualizan directamente las propiedades del objeto SQLAlchemy trackeado
        producto.sku = request.form.get('sku').strip()
        producto.nombre = request.form.get('nombre').strip()
        producto.cantidad_stock = cantidad_stock_nueva
        producto.precio_costo = float(request.form.get('precio_costo', 0.0))
        producto.precio_minimo = float(request.form.get('precio_minimo', 0.0))
        producto.precio_sugerido = float(request.form.get('precio_sugerido', 0.0))
        producto.observacion = request.form.get('observacion')
        
        try:
            if stock_anterior != cantidad_stock_nueva:
                ajuste = StockAdjustment(
                    product_id=producto.id,
                    admin_id=current_user.id,
                    tipo_movimiento='Ajuste Manual',
                    stock_anterior=stock_anterior,
                    stock_nuevo=cantidad_stock_nueva
                )
                db.session.add(ajuste)
                
            db.session.commit()
            flash('Producto actualizado correctamente en base de datos.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error en la base de datos al actualizar el producto.', 'danger')

    # El objeto producto se pasa a Jinja para auto-poblar (pre-llenar) el formulario en modo edición
    return render_template('inventory/form.html', producto=producto)

@inventory_bp.route('/historial-ajustes')
@login_required
@admin_required
def historial_ajustes():
    # joins implícitos a través de SQLAlchemy relationships se usan al acceder a las propiedades (ej. ajuste.producto.nombre),
    # o si se requiere optimización, se hace join explícito, pero iterar los proxies de ORM está bien para listas moderadas.
    ajustes = StockAdjustment.query.order_by(StockAdjustment.fecha_ajuste.desc()).all()
    return render_template('inventory/historial_ajustes.html', ajustes=ajustes)

@inventory_bp.route('/ver/<int:id>', methods=['GET'])
@login_required
@admin_required
def ver_producto(id):
    producto = Product.query.get_or_404(id)
    ajustes = StockAdjustment.query.filter_by(product_id=id).order_by(StockAdjustment.fecha_ajuste.desc()).all()
    return render_template('inventory/ver.html', producto=producto, ajustes=ajustes)
@inventory_bp.route('/carga_masiva', methods=['POST'])
@login_required
@admin_required
def carga_masiva():
    if 'archivo_excel' not in request.files:
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    file = request.files['archivo_excel']
    if file.filename == '':
        flash('El archivo no tiene nombre.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    try:
        # Leer el Excel usando pandas
        # Usamos BytesIO para leerlo directamente de memoria sin guardar en disco
        df = pd.read_excel(BytesIO(file.read()))
        
        # Validar columnas requeridas
        columnas_requeridas = ['nombre', 'sku', 'cantidad_stock', 'precio_costo', 'precio_minimo', 'precio_sugerido']
        for col in columnas_requeridas:
            if col not in df.columns:
                flash(f'Falta la columna requerida: {col}', 'danger')
                return redirect(url_for('inventory_bp.index'))

        productos_creados = 0
        productos_actualizados = 0

        for index, row in df.iterrows():
            sku = str(row['sku']).strip()
            nombre = str(row['nombre']).strip()
            cantidad = int(row['cantidad_stock'])
            p_costo = float(row['precio_costo'])
            p_minimo = float(row['precio_minimo'])
            p_sugerido = float(row['precio_sugerido'])
            obs = str(row['observacion']) if 'observacion' in df.columns and pd.notna(row['observacion']) else ""

            producto = Product.query.filter_by(sku=sku).first()

            if producto:
                # Actualizar existente
                stock_anterior = producto.cantidad_stock
                producto.nombre = nombre
                producto.cantidad_stock += cantidad # Sumamos la nueva cantidad
                producto.precio_costo = p_costo
                producto.precio_minimo = p_minimo
                producto.precio_sugerido = p_sugerido
                producto.observacion = obs
                
                # Registrar ajuste en Kardex
                ajuste = StockAdjustment(
                    product_id=producto.id,
                    admin_id=current_user.id,
                    tipo_movimiento='Carga Masiva (Update)',
                    stock_anterior=stock_anterior,
                    stock_nuevo=producto.cantidad_stock
                )
                db.session.add(ajuste)
                productos_actualizados += 1
            else:
                # Crear nuevo
                nuevo_prod = Product(
                    nombre=nombre,
                    sku=sku,
                    cantidad_stock=cantidad,
                    precio_costo=p_costo,
                    precio_minimo=p_minimo,
                    precio_sugerido=p_sugerido,
                    observacion=obs
                )
                db.session.add(nuevo_prod)
                db.session.flush() # Para obtener el ID antes del commit final

                # Registrar ajuste inicial en Kardex
                ajuste_inicial = StockAdjustment(
                    product_id=nuevo_prod.id,
                    admin_id=current_user.id,
                    tipo_movimiento='Carga Masiva (Nuevo)',
                    stock_anterior=0,
                    stock_nuevo=nuevo_prod.cantidad_stock
                )
                db.session.add(ajuste_inicial)
                productos_creados += 1

        db.session.commit()
        flash(f'Carga masiva completada: {productos_creados} productos creados y {productos_actualizados} productos actualizados.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar el archivo Excel: {str(e)}', 'danger')

    return redirect(url_for('inventory_bp.index'))
