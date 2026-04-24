from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Sale, SalePayment, ArqueoCaja, Expense, obtener_hora_bogota
from decorators import admin_required
from datetime import datetime

arqueo_bp = Blueprint('arqueo_bp', __name__)

@arqueo_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    # Obtener fecha de la URL o usar hoy
    fecha_str = request.args.get('fecha', obtener_hora_bogota().strftime('%Y-%m-%d'))
    try:
        fecha_seleccionada = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_seleccionada = obtener_hora_bogota().date()
        fecha_str = fecha_seleccionada.strftime('%Y-%m-%d')

    # Calcular ventas del día usando el desglose de pagos (SalePayment)
    # Esto permite que las ventas mixtas se repartan correctamente entre Efectivo y Transferencias
    ventas_ids = [v.id for v in Sale.query.filter(db.func.date(Sale.fecha_venta) == fecha_seleccionada).all()]
    pagos_del_dia = SalePayment.query.filter(SalePayment.sale_id.in_(ventas_ids)).all() if ventas_ids else []
    
    total_efectivo = sum(p.monto for p in pagos_del_dia if p.metodo_pago == 'efectivo')
    # Transferencias incluye todo lo que no sea efectivo (Nequi, Bancolombia, Daviplata, etc.)
    total_transferencias = sum(p.monto for p in pagos_del_dia if p.metodo_pago != 'efectivo')
    
    # Desglose para el tooltip
    total_nequi = sum(p.monto for p in pagos_del_dia if p.metodo_pago == 'nequi')
    total_bancolombia = sum(p.monto for p in pagos_del_dia if p.metodo_pago == 'bancolombia')
    total_daviplata = sum(p.monto for p in pagos_del_dia if p.metodo_pago == 'daviplata')

    # Solo gastos en EFECTIVO restan de la caja física.
    # Los gastos por transferencia no afectan los billetes en la registradora.
    gastos_diarios_registros = Expense.query.filter(
        db.func.date(Expense.fecha_gasto) == fecha_seleccionada,
        Expense.tipo_gasto == 'Gasto Diario',
        Expense.metodo_pago == 'efectivo'
    ).all()
    gastos_automaticos = float(sum(g.monto for g in gastos_diarios_registros))

    # Verificar si ya existe arqueo para esa fecha por este vendedor (Opcional, pero recomendado)
    arqueo_existente = ArqueoCaja.query.filter_by(fecha_arqueo=fecha_seleccionada, vendedor_id=current_user.id).first()

    if request.method == 'POST':
        base_inicial = float(request.form.get('base_inicial', 0.0))
        
        # Recalcular solo gastos en EFECTIVO por seguridad en el backend
        gastos_recalculados = Expense.query.filter(
            db.func.date(Expense.fecha_gasto) == fecha_seleccionada,
            Expense.tipo_gasto == 'Gasto Diario',
            Expense.metodo_pago == 'efectivo'
        ).all()
        gastos_del_dia = float(sum(g.monto for g in gastos_recalculados))
        
        observaciones_gastos = request.form.get('observaciones_gastos', '').strip()

        nuevo_arqueo = ArqueoCaja(
            vendedor_id=current_user.id,
            fecha_arqueo=fecha_seleccionada,
            base_inicial=base_inicial,
            gastos_del_dia=gastos_del_dia,
            observaciones_gastos=observaciones_gastos,
            total_efectivo_sistema=total_efectivo,
            total_nequi_sistema=total_nequi,
            total_daviplata_sistema=total_daviplata,
            total_bancolombia_sistema=total_bancolombia
        )

        try:
            db.session.add(nuevo_arqueo)
            db.session.commit()
            flash('Arqueo de caja guardado exitosamente.', 'success')
            return redirect(url_for('arqueo_bp.reporte', fecha_inicio=fecha_str, fecha_fin=fecha_str))
        except Exception as e:
            db.session.rollback()
            flash('Ocurrió un error al guardar el arqueo de caja.', 'danger')

    return render_template(
        'arqueo/form.html',
        fecha=fecha_str,
        total_efectivo=total_efectivo,
        total_nequi=total_nequi,
        total_bancolombia=total_bancolombia,
        total_daviplata=total_daviplata,
        total_transferencias=total_transferencias,
        venta_total=total_efectivo + total_transferencias,
        arqueo_existente=arqueo_existente,
        gastos_automaticos=gastos_automaticos
    )

@arqueo_bp.route('/reporte', methods=['GET'])
@login_required
def reporte():
    fecha_inicio_str = request.args.get('fecha_inicio', obtener_hora_bogota().strftime('%Y-%m-%d'))
    fecha_fin_str = request.args.get('fecha_fin', obtener_hora_bogota().strftime('%Y-%m-%d'))

    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_inicio = obtener_hora_bogota().date()
        fecha_fin = obtener_hora_bogota().date()

    # Si es admin puede ver todos los arqueos, si no, solo los suyos
    query = ArqueoCaja.query.filter(ArqueoCaja.fecha_arqueo >= fecha_inicio, ArqueoCaja.fecha_arqueo <= fecha_fin)
    
    if current_user.rol != 'admin':
        query = query.filter(ArqueoCaja.vendedor_id == current_user.id)

    arqueos_totales = query.order_by(ArqueoCaja.fecha_arqueo.desc()).all()
    
    page = request.args.get('page', 1, type=int)
    arqueos_paginados = query.order_by(ArqueoCaja.fecha_arqueo.desc()).paginate(page=page, per_page=15, error_out=False)

    # Cálculos globales para el reporte
    resumen = {
        'total_base': sum(a.base_inicial for a in arqueos_totales),
        'total_efectivo': sum(a.total_efectivo_sistema for a in arqueos_totales),
        'total_nequi': sum(a.total_nequi_sistema for a in arqueos_totales),
        'total_daviplata': sum(a.total_daviplata_sistema for a in arqueos_totales),
        'total_bancolombia': sum(a.total_bancolombia_sistema for a in arqueos_totales),
        'total_gastos': sum(a.gastos_del_dia for a in arqueos_totales)
    }
    
    resumen['total_recaudado'] = resumen['total_efectivo'] + resumen['total_nequi'] + resumen['total_daviplata'] + resumen['total_bancolombia']
    resumen['efectivo_esperado'] = (resumen['total_base'] + resumen['total_efectivo']) - resumen['total_gastos']

    fecha_generacion = obtener_hora_bogota().strftime('%Y-%m-%d %H:%M')

    # 2. Resumen de Productos Vendidos
    from models import SaleDetail, Product, ProductVariant
    from sqlalchemy import func
    
    # Filtramos ventas del rango
    ventas_rango_ids = [v.id for v in Sale.query.filter(func.date(Sale.fecha_venta) >= fecha_inicio, func.date(Sale.fecha_venta) <= fecha_fin).all()]
    
    detalles = SaleDetail.query.filter(SaleDetail.sale_id.in_(ventas_rango_ids)).all() if ventas_rango_ids else []
    
    productos_vendidos = {}
    for d in detalles:
        # Generar una clave única para agrupar por producto + variante
        key = f"{d.product_id}_{d.variant_id}" if not d.es_externo else f"EXT_{d.nombre_externo}"
        
        if key not in productos_vendidos:
            if d.es_externo:
                nombre = f"[EXT] {d.nombre_externo}"
            else:
                nombre = d.producto.nombre if d.producto else "Producto Desconocido"
                if d.variante:
                    nombre += f" - {d.variante.nombre_variante}"
            
            productos_vendidos[key] = {
                'nombre': nombre,
                'cantidad': 0,
                'monto': 0
            }
        
        productos_vendidos[key]['cantidad'] += d.cantidad_vendida
        productos_vendidos[key]['monto'] += float(d.cantidad_vendida * d.precio_venta_final)

    # Convertir a lista y ordenar por cantidad vendida (mayor a menor)
    lista_productos = sorted(productos_vendidos.values(), key=lambda x: x['cantidad'], reverse=True)

    return render_template(
        'arqueo/reporte.html',
        arqueos=arqueos_paginados,
        resumen=resumen,
        productos_vendidos=lista_productos,
        fecha_inicio=fecha_inicio_str,
        fecha_fin=fecha_fin_str,
        fecha_generacion=fecha_generacion
    )

@arqueo_bp.route('/eliminar/<int:arqueo_id>', methods=['POST'])
@login_required
@admin_required
def eliminar(arqueo_id):
    arqueo = ArqueoCaja.query.get_or_404(arqueo_id)
    fecha_arq = arqueo.fecha_arqueo
    try:
        db.session.delete(arqueo)
        db.session.commit()
        flash(f'Arqueo del {fecha_arq} revertido/eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al intentar revertir el arqueo.', 'danger')
    
    return redirect(request.referrer or url_for('arqueo_bp.reporte'))

