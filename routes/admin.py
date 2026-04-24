import calendar
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash

from models import db, Product, ProductVariant, Sale, User, Maneo, SaleDetail, SalePayment, StockAdjustment, Expense, StaffPayment, ProviderPayment, obtener_hora_bogota
from decorators import admin_required

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/vendedores', methods=['GET', 'POST'])
@login_required
@admin_required
def vendedores():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        telefono = request.form.get('telefono')
        password = request.form.get('password')
        
        # Se previene registrar vendedores con un mismo email para preservar la unicidad de las credenciales de acceso
        if User.query.filter_by(email=email).first():
            flash('Acción Denegada: Ese correo ya le pertenece a otro vendedor.', 'danger')
        else:
            try:
                # Se aplica un hash a la contraseña para evitar guardar texto plano, previniendo exposición en caso de brechas
                nuevo_vendedor = User(
                    nombre=nombre.strip(),
                    email=email.strip(),
                    telefono=telefono.strip() if telefono else None,
                    password_hash=generate_password_hash(password),
                    rol='vendedor'
                )
                db.session.add(nuevo_vendedor)
                db.session.commit()
                flash(f"¡Vendedor '{nombre}' registrado y autorizado para Cajas!", "success")
            except Exception as e:
                db.session.rollback()
                flash('Ocurrió un error en la base de datos al intentar registrar al vendedor.', 'danger')
            
        return redirect(url_for('admin_bp.vendedores'))
        
    # Se pasa la lista para poblar la tabla HTML de gestión de personal
    lista_vendedores = User.query.filter_by(rol='vendedor').order_by(User.nombre).all()
    
    # Historial de pagos al personal paginado
    page = request.args.get('page', 1, type=int)
    historial_pagos = StaffPayment.query.order_by(StaffPayment.fecha_pago.desc()).paginate(page=page, per_page=10, error_out=False)
    
    return render_template('admin/vendedores.html', vendedores=lista_vendedores, pagos=historial_pagos)


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_productos = Product.query.count()
    productos_bajo_stock = Product.query.filter(Product.cantidad_stock <= 5).count()
    maneos_activos = Maneo.query.filter_by(estado='PENDIENTE').count()
    total_ventas = db.session.query(func.sum(Sale.monto_total)).scalar() or 0.0

    from models import Provider
    total_proveedores = Provider.query.count()

    return render_template('admin/dashboard.html', 
                           total_productos=total_productos,
                           productos_bajo_stock=productos_bajo_stock,
                           total_ventas=total_ventas,
                           maneos_activos=maneos_activos,
                           total_proveedores=total_proveedores)

@admin_bp.route('/maneos')
@login_required
def maneos():
    lista_maneos = Maneo.query.order_by(Maneo.fecha_prestamo.desc()).all()
    # Priorizar PENDIENTE temporalmente
    lista_maneos.sort(key=lambda m: 0 if m.estado == 'PENDIENTE' else 1)
    
    productos = Product.query.order_by(Product.nombre).all()
    return render_template('admin/maneos.html', maneos=lista_maneos, productos=productos)

@admin_bp.route('/maneos/prestar', methods=['POST'])
@login_required
def maneos_prestar():
    sku = request.form.get('sku')
    cantidad = int(request.form.get('cantidad', 0))
    local_vecino = request.form.get('local_vecino')
    variant_id_str = request.form.get('variant_id')

    if not sku:
        flash('Asegúrate de escanear o ingresar un SKU válido.', 'danger')
        return redirect(url_for('admin_bp.maneos'))

    producto = Product.query.filter_by(sku=sku.strip()).first()
    if not producto:
        flash(f'Error: El producto con SKU "{sku}" no existe en el catálogo.', 'danger')
        return redirect(url_for('admin_bp.maneos'))

    # Determinar si se seleccionó una variante
    variante = None
    if variant_id_str and variant_id_str.strip():
        variante = ProductVariant.query.get(int(variant_id_str))
        if not variante or variante.product_id != producto.id:
            flash('La subcategoría seleccionada no pertenece a este producto.', 'danger')
            return redirect(url_for('admin_bp.maneos'))
        
        if variante.cantidad_stock < cantidad:
            flash(f'Stock insuficiente en la subcategoría "{variante.nombre_variante}" para prestar {cantidad} uds. (Stock actual: {variante.cantidad_stock}).', 'danger')
            return redirect(url_for('admin_bp.maneos'))
    else:
        if producto.cantidad_stock < cantidad:
            flash(f'Stock insuficiente para prestar {cantidad} unids. (Stock actual: {producto.cantidad_stock}).', 'danger')
            return redirect(url_for('admin_bp.maneos'))

    try:
        if variante:
            stock_anterior = variante.cantidad_stock
            variante.cantidad_stock -= cantidad
        else:
            stock_anterior = producto.cantidad_stock
            producto.cantidad_stock -= cantidad

        nuevo_maneo = Maneo(
            product_id=producto.id,
            variant_id=variante.id if variante else None,
            local_vecino=local_vecino.strip(),
            cantidad=cantidad,
            estado='PENDIENTE'
        )
        db.session.add(nuevo_maneo)

        ajuste = StockAdjustment(
            product_id=producto.id,
            admin_id=current_user.id,
            tipo_movimiento=f'Préstamo (Maneo) a {local_vecino}' + (f' [{variante.nombre_variante}]' if variante else ''),
            stock_anterior=stock_anterior,
            stock_nuevo=variante.cantidad_stock if variante else producto.cantidad_stock
        )
        db.session.add(ajuste)

        db.session.commit()
        flash('Maneo registrado y stock descontado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al registrar el maneo. Transacción revertida.', 'danger')

    return redirect(url_for('admin_bp.maneos'))

@admin_bp.route('/maneos/facturar/<int:id>', methods=['POST'])
@login_required
def maneos_facturar(id):
    maneo = Maneo.query.get_or_404(id)
    if maneo.estado != 'PENDIENTE':
        flash('Este maneo ya fue resuelto.', 'warning')
        return redirect(url_for('admin_bp.maneos'))
    
    # Determinar precios según variante o producto base
    if maneo.variante:
        precio_sugerido_ref = float(maneo.variante.precio_sugerido or maneo.producto.precio_sugerido)
        precio_costo_ref = float(maneo.variante.precio_costo or maneo.producto.precio_costo)
        precio_minimo_ref = float(maneo.variante.precio_minimo or maneo.producto.precio_minimo)
    else:
        precio_sugerido_ref = float(maneo.producto.precio_sugerido)
        precio_costo_ref = float(maneo.producto.precio_costo)
        precio_minimo_ref = float(maneo.producto.precio_minimo)

    cantidad_vendida = int(request.form.get('cantidad_vendida', maneo.cantidad))
    precio_venta = float(request.form.get('precio_venta', precio_sugerido_ref))
    metodo_pago = request.form.get('metodo_pago', 'efectivo')

    if cantidad_vendida <= 0 or cantidad_vendida > maneo.cantidad:
        flash(f'Operación rechazada: La cantidad vendida ({cantidad_vendida}) es inválida.', 'danger')
        return redirect(url_for('admin_bp.maneos'))

    precio_limite = precio_costo_ref if current_user.rol == 'admin' else precio_minimo_ref
    if float(precio_venta) < float(precio_limite):
        flash(f'Operación rechazada: El precio ingresado (${precio_venta}) es menor al límite autorizado (${precio_limite}).', 'danger')
        return redirect(url_for('admin_bp.maneos'))

    try:
        cantidad_no_vendida = maneo.cantidad - cantidad_vendida
        maneo.estado = 'FACTURADO'
        maneo.fecha_resolucion = obtener_hora_bogota()

        if cantidad_no_vendida > 0:
            if maneo.variante:
                stock_anterior = maneo.variante.cantidad_stock
                maneo.variante.cantidad_stock += cantidad_no_vendida
                stock_nuevo = maneo.variante.cantidad_stock
            else:
                stock_anterior = maneo.producto.cantidad_stock
                maneo.producto.cantidad_stock += cantidad_no_vendida
                stock_nuevo = maneo.producto.cantidad_stock

            variante_label = f' [{maneo.variante.nombre_variante}]' if maneo.variante else ''
            ajuste_retorno = StockAdjustment(
                product_id=maneo.product_id,
                admin_id=current_user.id,
                tipo_movimiento=f'Dev. Parcial de Maneo ({maneo.local_vecino}){variante_label}',
                stock_anterior=stock_anterior,
                stock_nuevo=stock_nuevo
            )
            db.session.add(ajuste_retorno)
            maneo.cantidad = cantidad_vendida

        # Registrar Venta
        nueva_venta = Sale(
            vendedor_id=current_user.id,
            monto_total=(precio_venta * cantidad_vendida),
            metodo_pago=metodo_pago
        )
        db.session.add(nueva_venta)
        db.session.flush()
        
        detalle = SaleDetail(
            sale_id=nueva_venta.id,
            product_id=maneo.product_id,
            variant_id=maneo.variant_id,
            cantidad_vendida=cantidad_vendida,
            precio_venta_final=precio_venta
        )
        db.session.add(detalle)

        db.session.commit()
        if cantidad_no_vendida > 0:
            flash(f'Maneo facturado parcialmente. Se vendieron {cantidad_vendida} y {cantidad_no_vendida} regresaron al inventario.', 'success')
        else:
            flash(f'Maneo facturado totalmente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al facturar el maneo.', 'danger')

    return redirect(url_for('admin_bp.maneos'))

@admin_bp.route('/maneos/devolver/<int:id>', methods=['POST'])
@login_required
def maneos_devolver(id):
    maneo = Maneo.query.get_or_404(id)
    if maneo.estado != 'PENDIENTE':
        flash('Este maneo ya fue resuelto.', 'warning')
        return redirect(url_for('admin_bp.maneos'))

    cantidad_devuelta = int(request.form.get('cantidad_devuelta', maneo.cantidad))
    if cantidad_devuelta <= 0 or cantidad_devuelta > maneo.cantidad:
        flash('Cantidad inválida para devolver.', 'danger')
        return redirect(url_for('admin_bp.maneos'))

    try:
        if maneo.variante:
            stock_anterior = maneo.variante.cantidad_stock
            maneo.variante.cantidad_stock += cantidad_devuelta
            stock_nuevo = maneo.variante.cantidad_stock
        else:
            stock_anterior = maneo.producto.cantidad_stock
            maneo.producto.cantidad_stock += cantidad_devuelta
            stock_nuevo = maneo.producto.cantidad_stock

        variante_label = f' [{maneo.variante.nombre_variante}]' if maneo.variante else ''
        ajuste = StockAdjustment(
            product_id=maneo.product_id,
            admin_id=current_user.id,
            tipo_movimiento=f'Devolución de Maneo ({maneo.local_vecino}){variante_label}',
            stock_anterior=stock_anterior,
            stock_nuevo=stock_nuevo
        )
        db.session.add(ajuste)

        if cantidad_devuelta >= maneo.cantidad:
            maneo.estado = 'DEVUELTO'
            maneo.fecha_resolucion = obtener_hora_bogota()
            flash(f'Maneo cerrado. Se devolvieron {cantidad_devuelta} unidades.', 'success')
        else:
            maneo.cantidad -= cantidad_devuelta
            flash(f'Devolución parcial: {cantidad_devuelta} uds devueltas. Quedan {maneo.cantidad} pendientes.', 'info')

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Error al procesar la devolución.', 'danger')

    return redirect(url_for('admin_bp.maneos'))

@admin_bp.route('/balance-financiero', methods=['GET', 'POST'])
@login_required
@admin_required
def balance_financiero():
    if request.method == 'POST':
        fecha_inicio_str = request.form.get('fecha_inicio')
        fecha_fin_str = request.form.get('fecha_fin')
    else:
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')

    hoy = obtener_hora_bogota()
    if not fecha_inicio_str or not fecha_fin_str:
        # Por defecto, el mes actual
        primer_dia = hoy.replace(day=1)
        ultimo_dia_mes = calendar.monthrange(hoy.year, hoy.month)[1]
        ultimo_dia = hoy.replace(day=ultimo_dia_mes)
        
        fecha_inicio_str = primer_dia.strftime('%Y-%m-%d')
        fecha_fin_str = ultimo_dia.strftime('%Y-%m-%d')

    try:
        inicio_dt = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        fin_dt = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
        # Avanzamos límite al inicio del siguiente día matemáticamente
        fin_dt_query = fin_dt + timedelta(days=1)
    except ValueError:
        flash("Formato de fecha inválido.", "danger")
        return redirect(url_for('admin_bp.dashboard'))

    # 1. Ventas Totales
    ventas_query = Sale.query.filter(Sale.fecha_venta >= inicio_dt, Sale.fecha_venta < fin_dt_query).all()
    
    ventas_efectivo = sum(v.monto_total for v in ventas_query if v.metodo_pago == 'efectivo')
    ventas_nequi = sum(v.monto_total for v in ventas_query if v.metodo_pago == 'nequi')
    ventas_bancolombia = sum(v.monto_total for v in ventas_query if v.metodo_pago == 'bancolombia')
    total_ingresos = ventas_efectivo + ventas_nequi + ventas_bancolombia

    # 2. Costo de Mercancía Vendida (COGS)
    detalles_vendidos = db.session.query(SaleDetail, Product).join(Product, SaleDetail.product_id == Product.id).join(Sale, SaleDetail.sale_id == Sale.id).filter(
        Sale.fecha_venta >= inicio_dt,
        Sale.fecha_venta < fin_dt_query
    ).all()
    
    costos_directos = sum((detalle.SaleDetail.cantidad_vendida * (detalle.Product.precio_costo or 0)) for detalle in detalles_vendidos)

    # 3. Costos Indirectos y Gastos Operativos (Gastos Generales)
    gastos_query = Expense.query.filter(Expense.fecha_gasto >= inicio_dt, Expense.fecha_gasto < fin_dt_query).all()
    
    costos_indirectos = sum(g.monto for g in gastos_query if g.tipo_gasto == 'Costo Indirecto')
    gastos_operacionales = sum(g.monto for g in gastos_query if g.tipo_gasto == 'Gasto Diario')

    # 4. Pagos a Proveedores (Abonos realizados en el periodo)
    pagos_prov_query = ProviderPayment.query.filter(ProviderPayment.fecha_pago >= inicio_dt, ProviderPayment.fecha_pago < fin_dt_query).all()
    total_pagos_proveedores = sum(p.monto_abonado for p in pagos_prov_query) or 0

    # 5. Pagos a Personal (Nómina)
    pagos_nomina_query = StaffPayment.query.filter(StaffPayment.fecha_pago >= inicio_dt, StaffPayment.fecha_pago < fin_dt_query).all()
    total_pagos_nomina = sum(p.monto for p in pagos_nomina_query) or 0
    
    total_salidas = float(costos_directos) + float(costos_indirectos) + float(gastos_operacionales) + float(total_pagos_proveedores) + float(total_pagos_nomina)
    balance_neto = float(total_ingresos) - total_salidas

    datos_financieros = {
        'ventas_efectivo': float(ventas_efectivo),
        'ventas_nequi': float(ventas_nequi),
        'ventas_bancolombia': float(ventas_bancolombia),
        'total_ingresos': float(total_ingresos),
        'costos_directos': float(costos_directos),
        'costos_indirectos': float(costos_indirectos),
        'gastos_operacionales': float(gastos_operacionales),
        'total_pagos_proveedores': float(total_pagos_proveedores),
        'total_pagos_nomina': float(total_pagos_nomina),
        'total_salidas': total_salidas,
        'balance_neto': balance_neto
    }

    return render_template(
        'admin/balance_reporte.html',
        fecha_inicio=fecha_inicio_str,
        fecha_fin=fecha_fin_str,
        fecha_generacion=hoy.strftime('%Y-%m-%d %H:%M'),
        datos=datos_financieros
    )


# ===================== PAGOS AL PERSONAL =====================

@admin_bp.route('/personal/pagar', methods=['POST'])
@login_required
@admin_required
def pagar_personal():
    """Registra un pago a un miembro del personal."""
    user_id = request.form.get('user_id', type=int)
    monto = float(request.form.get('monto', 0))
    observacion = request.form.get('observacion', '').strip()

    if not user_id or monto <= 0:
        flash('Debes seleccionar un empleado e ingresar un monto válido.', 'danger')
        return redirect(url_for('admin_bp.vendedores'))

    receptor = User.query.get(user_id)
    if not receptor:
        flash('El empleado seleccionado no existe.', 'danger')
        return redirect(url_for('admin_bp.vendedores'))

    try:
        pago = StaffPayment(
            user_id=receptor.id,
            monto=monto,
            observacion=observacion or None
        )
        db.session.add(pago)
        db.session.commit()
        flash(f'Pago de ${monto:,.2f} registrado para "{receptor.nombre}".', 'success')
        return redirect(url_for('admin_bp.comprobante_pago', id=pago.id))
    except Exception:
        db.session.rollback()
        flash('Error al registrar el pago en la base de datos.', 'danger')
        return redirect(url_for('admin_bp.vendedores'))


@admin_bp.route('/personal/comprobante/<int:id>')
@login_required
@admin_required
def comprobante_pago(id):
    """Muestra el comprobante imprimible de un pago al personal."""
    pago = StaffPayment.query.get_or_404(id)
    return render_template('admin/comprobante_pago.html', pago=pago)
