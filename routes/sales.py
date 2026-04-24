from flask import Blueprint, request, jsonify, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Product, ProductVariant, Sale, SaleDetail, SalePayment, StockAdjustment, obtener_hora_bogota
from decorators import admin_required
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

sales_bp = Blueprint('sales_bp', __name__)

@sales_bp.route('/nueva', methods=['GET', 'POST'])
@login_required # Importante: Te bloqueará el acceso si no hay current_user logeado (Flask-Login)
def procesar_venta():
    if request.method == 'GET':
        return render_template('sales/nueva.html')

    """
    PAYLOAD ESPERADO (JSON):
    {
        "items": [
            {
                "product_id": 5,              // NULL si es externo
                "variant_id": null,            // ID de variante o null
                "cantidad": 2,
                "precio_final": 15.50,
                "es_externo": false,
                "nombre_externo": null,
                "costo_externo": null
            }
        ],
        "pagos": [
            {"metodo": "efectivo", "monto": 20.00},
            {"metodo": "nequi",    "monto": 11.00}
        ],
        "fecha_venta": "2026-04-13",    // Opcional (solo admin)
        "multi_pago": true
    }
    """
    data = request.get_json()
    items = data.get('items', [])
    pagos = data.get('pagos', [])
    fecha_venta_str = data.get('fecha_venta')
    multi_pago = data.get('multi_pago', False)

    if not items:
        return jsonify({'error': 'No se enviaron productos para la venta'}), 400

    try:
        # ── Lógica de fecha retroactiva ──
        fecha_final = obtener_hora_bogota()
        if fecha_venta_str and current_user.rol == 'admin':
            try:
                fecha_final = datetime.strptime(fecha_venta_str, '%Y-%m-%d')
            except ValueError:
                pass

        # ── Validación de Pagos ──
        gran_total_items = Decimal('0.00')
        costo_total_items = Decimal('0.00')

        # Primer pase: calcular el gran total esperado
        for item in items:
            cantidad = int(item.get('cantidad', 0))
            precio_final = Decimal(str(item.get('precio_final', '0.00')))
            gran_total_items += precio_final * cantidad

        # Validar cuadre de pagos
        total_pagos = Decimal('0.00')
        metodo_pago_legacy = 'efectivo'

        if multi_pago and pagos:
            for p in pagos:
                total_pagos += Decimal(str(p.get('monto', '0.00')))
            
            if total_pagos != gran_total_items:
                diferencia = float(gran_total_items - total_pagos)
                return jsonify({
                    'error': f'Los pagos no cuadran con el total. Diferencia: ${diferencia:+.2f}. Total: ${float(gran_total_items):.2f}, Pagos: ${float(total_pagos):.2f}'
                }), 400
            
            # Legacy: guardar el primer método de pago
            metodo_pago_legacy = pagos[0].get('metodo', 'efectivo') if pagos else 'efectivo'
        else:
            # Pago único: tomar del primer pago o default
            if pagos and len(pagos) > 0:
                metodo_pago_legacy = pagos[0].get('metodo', 'efectivo')
                total_pagos = gran_total_items
            else:
                total_pagos = gran_total_items

        # ── Crear Venta Maestra ──
        nueva_venta = Sale(
            vendedor_id=current_user.id,
            monto_total=Decimal('0.00'),
            costo_total=Decimal('0.00'),
            utilidad=Decimal('0.00'),
            metodo_pago=metodo_pago_legacy,
            fecha_venta=fecha_final,
            estado='completada'
        )
        db.session.add(nueva_venta)
        db.session.flush()

        monto_total = Decimal('0.00')
        costo_total = Decimal('0.00')

        # ── Procesar cada ítem ──
        for item in items:
            es_externo = item.get('es_externo', False)
            cantidad = int(item.get('cantidad', 0))
            precio_final = Decimal(str(item.get('precio_final', '0.00')))

            if cantidad <= 0:
                raise ValueError("La cantidad vendida debe ser mayor a 0.")

            if es_externo:
                # ─── Producto Externo (Manual/Prestado) ───
                nombre_ext = item.get('nombre_externo', 'Producto Externo')
                costo_ext = Decimal(str(item.get('costo_externo', '0.00')))

                detalle = SaleDetail(
                    sale_id=nueva_venta.id,
                    product_id=None,
                    variant_id=None,
                    cantidad_vendida=cantidad,
                    precio_venta_final=precio_final,
                    costo_unitario=costo_ext,
                    es_externo=True,
                    nombre_externo=nombre_ext
                )
                db.session.add(detalle)
                monto_total += (precio_final * cantidad)
                costo_total += (costo_ext * cantidad)

            else:
                # ─── Producto del Inventario ───
                product_id = item.get('product_id')
                variant_id = item.get('variant_id')

                if variant_id:
                    # Producto CON variante
                    variante = ProductVariant.query.with_for_update().get(variant_id)
                    if not variante:
                        raise ValueError(f"La variante con ID {variant_id} no existe.")
                    
                    if cantidad > variante.cantidad_stock:
                        raise ValueError(f"Stock insuficiente para variante '{variante.nombre_variante}'. Disponible: {variante.cantidad_stock}.")

                    # Determinar precios (hereda del padre si no tiene propio)
                    producto_padre = Product.query.get(variante.product_id)
                    p_costo = variante.precio_costo or producto_padre.precio_costo
                    p_minimo = variante.precio_minimo or producto_padre.precio_minimo

                    precio_limite = p_costo if current_user.rol == 'admin' else p_minimo
                    if precio_final < precio_limite:
                        raise ValueError(f"No autorizado: Precio ({precio_final}) inferior al límite ({precio_limite}) para '{variante.nombre_variante}'.")

                    # Debitar stock de la variante
                    stock_anterior = variante.cantidad_stock
                    variante.cantidad_stock -= cantidad

                    # Registrar en el Kardex
                    ajuste = StockAdjustment(
                        product_id=variante.product_id,
                        variant_id=variante.id,
                        admin_id=current_user.id,
                        tipo_movimiento=f'Salida de Venta #{nueva_venta.id}',
                        stock_anterior=stock_anterior,
                        stock_nuevo=variante.cantidad_stock
                    )
                    db.session.add(ajuste)

                    detalle = SaleDetail(
                        sale_id=nueva_venta.id,
                        product_id=variante.product_id,
                        variant_id=variante.id,
                        cantidad_vendida=cantidad,
                        precio_venta_final=precio_final,
                        costo_unitario=p_costo,
                        es_externo=False
                    )
                    db.session.add(detalle)
                    monto_total += (precio_final * cantidad)
                    costo_total += (p_costo * cantidad)

                else:
                    # Producto SIMPLE (sin variante)
                    producto = Product.query.with_for_update().get(product_id)
                    if not producto:
                        raise ValueError(f"El producto con ID {product_id} no existe.")

                    if cantidad > producto.cantidad_stock:
                        raise ValueError(f"Stock insuficiente para '{producto.nombre}'. Solicitado: {cantidad}, Disponible: {producto.cantidad_stock}.")

                    precio_limite = producto.precio_costo if current_user.rol == 'admin' else producto.precio_minimo
                    if precio_final < precio_limite:
                        raise ValueError(f"No autorizado: Precio ({precio_final}) inferior al límite ({precio_limite}) para '{producto.nombre}'.")

                    # Debitar stock maestro
                    stock_anterior = producto.cantidad_stock
                    producto.cantidad_stock -= cantidad

                    # Registrar en el Kardex
                    ajuste = StockAdjustment(
                        product_id=producto.id,
                        variant_id=None,
                        admin_id=current_user.id,
                        tipo_movimiento=f'Salida de Venta #{nueva_venta.id}',
                        stock_anterior=stock_anterior,
                        stock_nuevo=producto.cantidad_stock
                    )
                    db.session.add(ajuste)

                    detalle = SaleDetail(
                        sale_id=nueva_venta.id,
                        product_id=producto.id,
                        variant_id=None,
                        cantidad_vendida=cantidad,
                        precio_venta_final=precio_final,
                        costo_unitario=producto.precio_costo,
                        es_externo=False
                    )
                    db.session.add(detalle)
                    monto_total += (precio_final * cantidad)
                    costo_total += (producto.precio_costo * cantidad)

        # ── Registrar Pagos ──
        if multi_pago and pagos:
            for p in pagos:
                pago = SalePayment(
                    sale_id=nueva_venta.id,
                    metodo_pago=p.get('metodo', 'efectivo'),
                    monto=Decimal(str(p.get('monto', '0.00')))
                )
                db.session.add(pago)
        else:
            # Pago único
            pago = SalePayment(
                sale_id=nueva_venta.id,
                metodo_pago=metodo_pago_legacy,
                monto=monto_total
            )
            db.session.add(pago)

        # ── Actualizar la Venta Maestra ──
        nueva_venta.monto_total = monto_total
        nueva_venta.costo_total = costo_total
        nueva_venta.utilidad = monto_total - costo_total

        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Venta registrada e inventario descontado con éxito.',
            'sale_id': nueva_venta.id,
            'total': str(monto_total)
        }), 201

    except ValueError as val_err:
        db.session.rollback()
        return jsonify({'error': str(val_err)}), 400
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Ocurrió un error interno al procesar la venta.'}), 500

# Endpoint API asíncrono para el escáner del Punto de Venta
@sales_bp.route('/api/producto/<string:sku>', methods=['GET'])
@login_required
def api_buscar_producto(sku):
    producto = Product.query.filter_by(sku=sku).first()
    
    if not producto:
        return jsonify({'error': 'Código SKU no encontrado en el sistema'}), 404

    # Verificar si tiene variantes con stock
    variantes_raw = ProductVariant.query.filter_by(product_id=producto.id).all()
    variantes_con_stock = []
    
    for v in variantes_raw:
        variantes_con_stock.append({
            'id': v.id,
            'nombre': v.nombre_variante,
            'sku': v.sku_variante,
            'cantidad_stock': v.cantidad_stock,
            'precio_costo': float(v.precio_costo or producto.precio_costo),
            'precio_minimo': float(v.precio_minimo or producto.precio_minimo),
            'precio_sugerido': float(v.precio_sugerido or producto.precio_sugerido),
            'precio_limite': float(v.precio_costo or producto.precio_costo) if current_user.rol == 'admin' else float(v.precio_minimo or producto.precio_minimo)
        })

    tiene_variantes = len(variantes_con_stock) > 0
        
    return jsonify({
        'id': producto.id,
        'nombre': producto.nombre,
        'sku': producto.sku,
        'cantidad_stock': producto.total_stock,
        'precio_costo': float(producto.precio_costo),
        'precio_minimo': float(producto.precio_minimo),
        'precio_limite': float(producto.precio_costo) if current_user.rol == 'admin' else float(producto.precio_minimo),
        'precio_sugerido': float(producto.precio_sugerido),
        'tiene_variantes': tiene_variantes,
        'variantes': variantes_con_stock
    })

# Ruta para la Impresión del formato Térmico (Ticket)
@sales_bp.route('/recibo/<int:sale_id>', methods=['GET'])
@login_required # Proteger confidencialidad del cajero
def imprimir_ticket(sale_id):
    # Regla: Retorna 404 si alguien ingresa un ID falso
    venta = Sale.query.options(
        joinedload(Sale.detalles),
        joinedload(Sale.pagos),
        joinedload(Sale.vendedor)
    ).get_or_404(sale_id)
    return render_template('sales/ticket.html', venta=venta)

# Endpoint Historial de Ventas (Administradores)
@sales_bp.route('/historial', methods=['GET'])
@login_required
@admin_required
def historial():
    # Calcular el valor exacto de 'HOY' en Bogotá
    hoy_bogota = obtener_hora_bogota().strftime('%Y-%m-%d')
    
    # Si existen los args, los usa, de lo contrario colapsa a HOY por defecto
    fecha_inicio = request.args.get('fecha_inicio', hoy_bogota)
    fecha_fin = request.args.get('fecha_fin', hoy_bogota)
    
    # Optimización: eager loading (evita N+1 con joinedload)
    query = Sale.query.options(joinedload(Sale.vendedor), joinedload(Sale.pagos))
    
    # Motor de búsqueda por Rango Restricto
    if fecha_inicio:
        inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        query = query.filter(Sale.fecha_venta >= inicio_dt)
        
    if fecha_fin:
        fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
        # Sumar 1 día matemáticamente para incluir los registros hasta las 23:59:59 del último día
        query = query.filter(Sale.fecha_venta < fin_dt + timedelta(days=1))
        
    ventas_totales = query.order_by(Sale.fecha_venta.desc()).all()
    
    page = request.args.get('page', 1, type=int)
    ventas_paginadas = query.order_by(Sale.fecha_venta.desc()).paginate(page=page, per_page=15, error_out=False)
    
    # Auditar y cruzar sumatorios de métricas de pago (ahora desde SalePayment)
    total_efectivo = Decimal('0.00')
    total_nequi = Decimal('0.00')
    total_daviplata = Decimal('0.00')
    total_bancolombia = Decimal('0.00')

    for v in ventas_totales:
        if v.pagos:
            for p in v.pagos:
                if p.metodo_pago == 'efectivo':
                    total_efectivo += p.monto
                elif p.metodo_pago == 'nequi':
                    total_nequi += p.monto
                elif p.metodo_pago == 'daviplata':
                    total_daviplata += p.monto
                elif p.metodo_pago == 'bancolombia':
                    total_bancolombia += p.monto
        else:
            # Compatibilidad con ventas legacy sin SalePayment
            if v.metodo_pago == 'efectivo':
                total_efectivo += v.monto_total
            elif v.metodo_pago == 'nequi':
                total_nequi += v.monto_total
            elif v.metodo_pago == 'daviplata':
                total_daviplata += v.monto_total
            elif v.metodo_pago == 'bancolombia':
                total_bancolombia += v.monto_total

    # Envío al Engine de HTML
    return render_template('sales/historial.html', 
                           ventas=ventas_paginadas, 
                           total_efectivo=total_efectivo,
                           total_nequi=total_nequi,
                           total_daviplata=total_daviplata,
                           total_bancolombia=total_bancolombia,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)


# Endpoint Catálogo Estricto de solo vista para Operarios
@sales_bp.route('/catalogo', methods=['GET'])
@login_required 
def catalogo():
    query_str = request.args.get('q', '').strip()
    
    if query_str:
        # Motor de similitud Case-Insensitive (Like)
        search_term = f"%{query_str}%"
        productos = Product.query.filter(
            or_(
                Product.sku.ilike(search_term), 
                Product.nombre.ilike(search_term)
            )
        ).limit(50).all()
    else:
        # Límite pasivo de 50 ítems para ahorrar memoria RAM de BD en carga inicial
        productos = Product.query.limit(50).all()
        
    return render_template('sales/catalogo.html', productos=productos, q=query_str)
@sales_bp.route('/eliminar/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def eliminar_venta(sale_id):
    """Elimina una venta y devuelve el stock al inventario."""
    venta = Sale.query.get_or_404(sale_id)
    
    try:
        # Revertir stock de cada detalle
        for detalle in venta.detalles:
            if not detalle.es_externo:
                if detalle.variant_id:
                    variante = ProductVariant.query.get(detalle.variant_id)
                    if variante:
                        stock_anterior = variante.cantidad_stock
                        variante.cantidad_stock += detalle.cantidad_vendida
                        
                        # Registrar en el Kardex
                        ajuste = StockAdjustment(
                            product_id=variante.product_id,
                            variant_id=variante.id,
                            admin_id=current_user.id,
                            tipo_movimiento=f'Devolución por Eliminación Venta #{venta.id}',
                            stock_anterior=stock_anterior,
                            stock_nuevo=variante.cantidad_stock
                        )
                        db.session.add(ajuste)
                        
                        # Actualizar stock total del padre si es necesario (dependiendo de la implementación)
                        # Como Product.total_stock es una property, no hace falta actualizar columna si solo se usa la property.
                        # Pero en Sora solemos sincronizar Product.cantidad_stock.
                        padre = Product.query.get(variante.product_id)
                        if padre:
                            padre.cantidad_stock += detalle.cantidad_vendida
                else:
                    producto = Product.query.get(detalle.product_id)
                    if producto:
                        stock_anterior = producto.cantidad_stock
                        producto.cantidad_stock += detalle.cantidad_vendida
                        
                        # Registrar en el Kardex
                        ajuste = StockAdjustment(
                            product_id=producto.id,
                            variant_id=None,
                            admin_id=current_user.id,
                            tipo_movimiento=f'Devolución por Eliminación Venta #{venta.id}',
                            stock_anterior=stock_anterior,
                            stock_nuevo=producto.cantidad_stock
                        )
                        db.session.add(ajuste)

        db.session.delete(venta)
        db.session.commit()
        flash(f'Venta #{sale_id} eliminada y stock devuelto al inventario.', 'success')
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash('Error al eliminar la venta y revertir el stock.', 'danger')

    return redirect(url_for('sales_bp.historial'))
