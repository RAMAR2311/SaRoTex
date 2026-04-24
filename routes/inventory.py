import os
import pandas as pd
from io import BytesIO
from werkzeug.utils import secure_filename
from flask import current_app, Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Product, StockAdjustment, ProductVariant
from decorators import admin_required

inventory_bp = Blueprint('inventory_bp', __name__)

@inventory_bp.route('/', methods=['GET'])
@login_required
@admin_required
def index():
    # Calcular KPIs globales del inventario
    productos_todos = Product.query.all()
    total_productos_stock = 0
    costo_total_inventario = 0.0
    valor_venta_inventario = 0.0

    for p in productos_todos:
        if p.variantes:
            for v in p.variantes:
                total_productos_stock += v.cantidad_stock
                pc = float(v.precio_costo) if v.precio_costo is not None else float(p.precio_costo)
                ps = float(v.precio_sugerido) if v.precio_sugerido is not None else float(p.precio_sugerido)
                costo_total_inventario += pc * v.cantidad_stock
                valor_venta_inventario += ps * v.cantidad_stock
        else:
            total_productos_stock += p.cantidad_stock
            costo_total_inventario += float(p.precio_costo) * p.cantidad_stock
            valor_venta_inventario += float(p.precio_sugerido) * p.cantidad_stock

    page = request.args.get('page', 1, type=int)
    # Paginar a 15 productos por página para la tabla
    productos_paginated = Product.query.order_by(Product.nombre).paginate(page=page, per_page=15, error_out=False)
    
    return render_template('inventory/index.html', 
                           productos=productos_paginated,
                           total_productos_stock=total_productos_stock,
                           costo_total_inventario=costo_total_inventario,
                           valor_venta_inventario=valor_venta_inventario)

@inventory_bp.route('/producto/<int:id>/agregar_variante', methods=['POST'])
@login_required
@admin_required
def agregar_variante(id):
    producto = Product.query.get_or_404(id)
    nombre_variante = request.form.get('nombre_variante')
    cantidad_stock = int(request.form.get('cantidad_stock', 0))
    
    precio_costo_req = request.form.get('precio_costo')
    precio_minimo_req = request.form.get('precio_minimo')
    precio_sugerido_req = request.form.get('precio_sugerido')

    if not nombre_variante:
        flash('El nombre de la subcategoría es obligatorio.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    # Guardar stock anterior del producto padre
    stock_anterior = producto.total_stock

    nueva_variante = ProductVariant(
        product_id=producto.id,
        nombre_variante=nombre_variante,
        cantidad_stock=cantidad_stock,
        precio_costo=float(precio_costo_req) if precio_costo_req else producto.precio_costo,
        precio_minimo=float(precio_minimo_req) if precio_minimo_req else producto.precio_minimo,
        precio_sugerido=float(precio_sugerido_req) if precio_sugerido_req else producto.precio_sugerido
    )
    try:
        db.session.add(nueva_variante)
        db.session.commit()
        
        stock_nuevo = producto.total_stock
        ajuste = StockAdjustment(
            product_id=producto.id,
            admin_id=current_user.id,
            tipo_movimiento=f'Agregó subcat: {nombre_variante}',
            stock_anterior=stock_anterior,
            stock_nuevo=stock_nuevo
        )
        db.session.add(ajuste)
        db.session.commit()

        flash(f'Subcategoría "{nombre_variante}" agregada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al agregar la subcategoría.', 'danger')

    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/variante/<int:id>/editar', methods=['POST'])
@login_required
@admin_required
def editar_variante(id):
    variante = ProductVariant.query.get_or_404(id)
    producto = variante.producto_padre
    
    stock_anterior = producto.total_stock
    nombre_anterior = variante.nombre_variante
    
    variante.nombre_variante = request.form.get('nombre_variante')
    variante.cantidad_stock = int(request.form.get('cantidad_stock', variante.cantidad_stock))
    
    precio_costo_req = request.form.get('precio_costo')
    precio_minimo_req = request.form.get('precio_minimo')
    precio_sugerido_req = request.form.get('precio_sugerido')
    
    if precio_costo_req: variante.precio_costo = float(precio_costo_req)
    if precio_minimo_req: variante.precio_minimo = float(precio_minimo_req)
    if precio_sugerido_req: variante.precio_sugerido = float(precio_sugerido_req)
    
    try:
        db.session.commit()
        
        stock_nuevo = producto.total_stock
        if stock_anterior != stock_nuevo:
            ajuste = StockAdjustment(
                product_id=producto.id,
                admin_id=current_user.id,
                tipo_movimiento=f'Editó subcat: {nombre_anterior}',
                stock_anterior=stock_anterior,
                stock_nuevo=stock_nuevo
            )
            db.session.add(ajuste)
            db.session.commit()
            
        flash('Subcategoría editada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al editar la subcategoría.', 'danger')
        
    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/variante/<int:id>/eliminar', methods=['POST'])
@login_required
@admin_required
def eliminar_variante(id):
    variante = ProductVariant.query.get_or_404(id)
    
    from models import SaleDetail
    if SaleDetail.query.filter_by(variant_id=variante.id).first():
        flash('Acción denegada: No se puede eliminar una subcategoría que tiene ventas facturadas.', 'warning')
        return redirect(url_for('inventory_bp.index'))
        
    try:
        producto = variante.producto_padre
        stock_anterior = producto.total_stock
        nombre = variante.nombre_variante
        
        db.session.delete(variante)
        db.session.commit()
        
        stock_nuevo = producto.total_stock
        ajuste = StockAdjustment(
            product_id=producto.id,
            admin_id=current_user.id,
            tipo_movimiento=f'Eliminó subcat: {nombre}',
            stock_anterior=stock_anterior,
            stock_nuevo=stock_nuevo
        )
        db.session.add(ajuste)
        db.session.commit()
        
        flash(f'La subcategoría "{nombre}" fue borrada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la subcategoría: {str(e)}', 'danger')
        
    return redirect(url_for('inventory_bp.index'))

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

        # Recibir variantes del formulario
        v_nombres = request.form.getlist('v_nombre[]')
        v_stocks = request.form.getlist('v_stock[]')
        v_costos = request.form.getlist('v_costo[]')
        v_mins = request.form.getlist('v_min[]')
        v_sugs = request.form.getlist('v_sug[]')

        # Si hay variantes, el stock base del maestro se pone en 0
        stock_base = 0 if v_nombres else int(request.form.get('cantidad_stock', 0))

        nuevo_prod = Product(
            sku=request.form.get('sku').strip(),
            nombre=request.form.get('nombre').strip(),
            cantidad_stock=stock_base,
            precio_costo=float(request.form.get('precio_costo', 0.0)),
            precio_minimo=float(request.form.get('precio_minimo', 0.0)),
            precio_sugerido=float(request.form.get('precio_sugerido', 0.0)),
            imagen=imagen_filename,
            observacion=request.form.get('observacion')
        )
        try:
            db.session.add(nuevo_prod)
            db.session.flush() # Para obtener ID
            
            # Crear subcategorías si existen
            for i in range(len(v_nombres)):
                if not v_nombres[i]: continue
                nueva_v = ProductVariant(
                    product_id=nuevo_prod.id,
                    nombre_variante=v_nombres[i],
                    cantidad_stock=int(v_stocks[i] or 0),
                    precio_costo=float(v_costos[i]) if v_costos[i] else nuevo_prod.precio_costo,
                    precio_minimo=float(v_mins[i]) if v_mins[i] else nuevo_prod.precio_minimo,
                    precio_sugerido=float(v_sugs[i]) if v_sugs[i] else nuevo_prod.precio_sugerido
                )
                db.session.add(nueva_v)

            db.session.commit()
            
            # Crear ajuste inicial en el Kardex
            ajuste_inicial = StockAdjustment(
                product_id=nuevo_prod.id,
                admin_id=current_user.id,
                tipo_movimiento='Creación Inicial' + (' (con Subcategorías)' if v_nombres else ''),
                stock_anterior=0,
                stock_nuevo=nuevo_prod.total_stock
            )
            db.session.add(ajuste_inicial)
            db.session.commit()

            flash('Producto y subcategorías creados exitosamente.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {str(e)}', 'danger')
            
    return render_template('inventory/form.html')

@inventory_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_producto(id):
    producto = Product.query.get_or_404(id)
    
    if request.method == 'POST':
        stock_total_anterior = producto.total_stock
        
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                producto.imagen = filename
                
        producto.sku = request.form.get('sku').strip()
        producto.nombre = request.form.get('nombre').strip()
        producto.precio_costo = float(request.form.get('precio_costo', 0.0))
        producto.precio_minimo = float(request.form.get('precio_minimo', 0.0))
        producto.precio_sugerido = float(request.form.get('precio_sugerido', 0.0))
        producto.observacion = request.form.get('observacion')

        # Sincronización de Subcategorías
        v_ids = request.form.getlist('variant_id[]')
        v_nombres = request.form.getlist('v_nombre[]')
        v_stocks = request.form.getlist('v_stock[]')
        v_costos = request.form.getlist('v_costo[]')
        v_mins = request.form.getlist('v_min[]')
        v_sugs = request.form.getlist('v_sug[]')

        ids_en_formulario = [int(vid) for vid in v_ids if vid]
        
        # 1. Eliminar las que ya no están
        for v_existente in producto.variantes[:]:
            if v_existente.id not in ids_en_formulario:
                db.session.delete(v_existente)
        
        # 2. Actualizar o crear
        if not v_nombres:
            producto.cantidad_stock = int(request.form.get('cantidad_stock', 0))
        else:
            producto.cantidad_stock = 0
            for i in range(len(v_nombres)):
                nombre_v = v_nombres[i]
                if not nombre_v: continue
                
                vid = v_ids[i] if i < len(v_ids) else None
                stock_v = int(v_stocks[i] or 0)
                costo_v = float(v_costos[i]) if v_costos[i] else producto.precio_costo
                min_v = float(v_mins[i]) if v_mins[i] else producto.precio_minimo
                sug_v = float(v_sugs[i]) if v_sugs[i] else producto.precio_sugerido

                if vid:
                    v_obj = ProductVariant.query.get(int(vid))
                    if v_obj:
                        v_obj.nombre_variante = nombre_v
                        v_obj.cantidad_stock = stock_v
                        v_obj.precio_costo = costo_v
                        v_obj.precio_minimo = min_v
                        v_obj.precio_sugerido = sug_v
                else:
                    nueva_v = ProductVariant(
                        product_id=producto.id,
                        nombre_variante=nombre_v,
                        cantidad_stock=stock_v,
                        precio_costo=costo_v,
                        precio_minimo=min_v,
                        precio_sugerido=sug_v
                    )
                    db.session.add(nueva_v)

        try:
            db.session.commit()
            
            # Registrar ajuste si el TOTAL cambió
            stock_total_nuevo = producto.total_stock
            if stock_total_anterior != stock_total_nuevo:
                ajuste = StockAdjustment(
                    product_id=producto.id,
                    admin_id=current_user.id,
                    tipo_movimiento='Ajuste en Edición (Subcategorías)',
                    stock_anterior=stock_total_anterior,
                    stock_nuevo=stock_total_nuevo
                )
                db.session.add(ajuste)
                db.session.commit()
                
            flash('Producto actualizado correctamente.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

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
        
        # Validar columnas requeridas (ahora soportando variantes)
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
            cantidad = int(row['cantidad_stock']) if pd.notna(row['cantidad_stock']) else 0
            p_costo = float(row['precio_costo']) if pd.notna(row['precio_costo']) else 0.0
            p_minimo = float(row['precio_minimo']) if pd.notna(row['precio_minimo']) else 0.0
            p_sugerido = float(row['precio_sugerido']) if pd.notna(row['precio_sugerido']) else 0.0
            obs = str(row['observacion']) if 'observacion' in df.columns and pd.notna(row['observacion']) else ""
            
            nombre_v = str(row['nombre_variante']).strip() if 'nombre_variante' in df.columns and pd.notna(row['nombre_variante']) else ""
            if nombre_v.lower() == 'nan':
                nombre_v = ""

            producto = Product.query.filter_by(sku=sku).first()

            # 1. Crear producto padre si no existe
            if not producto:
                producto = Product(
                    nombre=nombre,
                    sku=sku,
                    cantidad_stock=cantidad if not nombre_v else 0, # Si es variante, el padre empieza sin stock directo
                    precio_costo=p_costo,
                    precio_minimo=p_minimo,
                    precio_sugerido=p_sugerido,
                    observacion=obs
                )
                db.session.add(producto)
                db.session.flush() # Obtener ID
                productos_creados += 1

                if not nombre_v:
                    ajuste_inicial = StockAdjustment(
                        product_id=producto.id,
                        admin_id=current_user.id,
                        tipo_movimiento='Carga Masiva (Nuevo Padre)',
                        stock_anterior=0,
                        stock_nuevo=producto.cantidad_stock
                    )
                    db.session.add(ajuste_inicial)
            else:
                # 2. Actualizar producto padre si no es una línea de variante
                if not nombre_v:
                    stock_anterior = producto.cantidad_stock
                    producto.nombre = nombre
                    producto.cantidad_stock += cantidad
                    producto.precio_costo = p_costo
                    producto.precio_minimo = p_minimo
                    producto.precio_sugerido = p_sugerido
                    producto.observacion = obs
                    
                    ajuste = StockAdjustment(
                        product_id=producto.id,
                        admin_id=current_user.id,
                        tipo_movimiento='Carga Masiva (Update Padre)',
                        stock_anterior=stock_anterior,
                        stock_nuevo=producto.cantidad_stock
                    )
                    db.session.add(ajuste)
                    productos_actualizados += 1

            # 3. Manejar la Variante si aplica
            if nombre_v:
                variante = ProductVariant.query.filter_by(product_id=producto.id, nombre_variante=nombre_v).first()
                if variante:
                    variante.cantidad_stock += cantidad
                    variante.precio_costo = p_costo
                    variante.precio_minimo = p_minimo
                    variante.precio_sugerido = p_sugerido
                    productos_actualizados += 1
                else:
                    nueva_variante = ProductVariant(
                        product_id=producto.id,
                        nombre_variante=nombre_v,
                        cantidad_stock=cantidad,
                        precio_costo=p_costo,
                        precio_minimo=p_minimo,
                        precio_sugerido=p_sugerido
                    )
                    db.session.add(nueva_variante)
                    productos_creados += 1

        db.session.commit()
        flash(f'Carga masiva completada: {productos_creados} registros creados y {productos_actualizados} registros actualizados.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar el archivo Excel: {str(e)}', 'danger')

    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_producto(id):
    producto = Product.query.get_or_404(id)
    try:
        # Eliminar imagen física del servidor si existe
        if producto.imagen:
            image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], producto.imagen)
            if os.path.exists(image_path):
                os.remove(image_path)
        
        db.session.delete(producto)
        db.session.commit()
        flash('Producto eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        # El error suele ser por integridad referencial (ventas ya registradas)
        flash('No se puede eliminar el producto porque tiene ventas u otros registros asociados.', 'danger')
        
    return redirect(url_for('inventory_bp.index'))
