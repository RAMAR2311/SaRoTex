from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Provider, ProviderDelivery, ProviderPayment, Product, StockAdjustment
from decorators import admin_required

providers_bp = Blueprint('providers_bp', __name__)


@providers_bp.route('/')
@login_required
@admin_required
def index():
    """Lista todos los proveedores registrados."""
    proveedores = Provider.query.order_by(Provider.nombre).all()
    return render_template('providers/index.html', proveedores=proveedores)


@providers_bp.route('/crear', methods=['POST'])
@login_required
@admin_required
def crear():
    """Registra un nuevo proveedor en el sistema."""
    nombre = request.form.get('nombre', '').strip()
    telefono = request.form.get('telefono', '').strip()
    empresa = request.form.get('empresa', '').strip()

    if not nombre:
        flash('El nombre del proveedor es obligatorio.', 'danger')
        return redirect(url_for('providers_bp.index'))

    try:
        nuevo_proveedor = Provider(
            nombre=nombre,
            telefono=telefono or None,
            empresa=empresa or None
        )
        db.session.add(nuevo_proveedor)
        db.session.commit()
        flash(f"Proveedor '{nombre}' registrado exitosamente.", 'success')
    except Exception:
        db.session.rollback()
        flash('Error al registrar el proveedor en la base de datos.', 'danger')

    return redirect(url_for('providers_bp.index'))


@providers_bp.route('/<int:id>')
@login_required
@admin_required
def cuenta(id):
    """Vista de cuenta individual del proveedor con saldo pendiente."""
    proveedor = Provider.query.get_or_404(id)

    # Calcular totales históricos
    total_entregas = sum(e.costo_total for e in proveedor.entregas) or 0
    total_abonos = sum(p.monto_abonado for p in proveedor.pagos) or 0
    saldo_pendiente = float(total_entregas) - float(total_abonos)

    # Productos disponibles para el selector de entregas
    productos = Product.query.order_by(Product.nombre).all()

    return render_template(
        'providers/cuenta.html',
        proveedor=proveedor,
        total_entregas=float(total_entregas),
        total_abonos=float(total_abonos),
        saldo_pendiente=saldo_pendiente,
        productos=productos
    )


@providers_bp.route('/<int:id>/delivery', methods=['POST'])
@login_required
@admin_required
def registrar_entrega(id):
    """Registra una entrega de mercancía y actualiza el stock del producto."""
    proveedor = Provider.query.get_or_404(id)

    product_id = request.form.get('product_id', type=int)
    cantidad_entregada = request.form.get('cantidad_entregada', 0, type=int)
    costo_unitario = float(request.form.get('costo_unitario', 0))

    if not product_id or cantidad_entregada <= 0 or costo_unitario <= 0:
        flash('Todos los campos de la entrega son obligatorios y deben ser mayores a 0.', 'danger')
        return redirect(url_for('providers_bp.cuenta', id=id))

    producto = Product.query.get(product_id)
    if not producto:
        flash('El producto seleccionado no existe en el inventario.', 'danger')
        return redirect(url_for('providers_bp.cuenta', id=id))

    costo_total = round(costo_unitario * cantidad_entregada, 2)

    try:
        # Registrar la entrega del proveedor
        entrega = ProviderDelivery(
            provider_id=proveedor.id,
            product_id=producto.id,
            cantidad_entregada=cantidad_entregada,
            costo_unitario=costo_unitario,
            costo_total=costo_total
        )
        db.session.add(entrega)

        # Actualizar stock del producto en inventario
        stock_anterior = producto.cantidad_stock
        producto.cantidad_stock += cantidad_entregada

        # Registrar en el Kardex de ajustes
        ajuste = StockAdjustment(
            product_id=producto.id,
            admin_id=current_user.id,
            tipo_movimiento=f'Entrega de Proveedor ({proveedor.nombre})',
            stock_anterior=stock_anterior,
            stock_nuevo=producto.cantidad_stock
        )
        db.session.add(ajuste)

        db.session.commit()
        flash(f'Entrega registrada: +{cantidad_entregada} unids. de "{producto.nombre}" al inventario.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al registrar la entrega en la base de datos.', 'danger')

    return redirect(url_for('providers_bp.cuenta', id=id))


@providers_bp.route('/<int:id>/payment', methods=['POST'])
@login_required
@admin_required
def registrar_pago(id):
    """Registra un abono o pago al proveedor."""
    proveedor = Provider.query.get_or_404(id)

    monto = float(request.form.get('monto_abonado', 0))
    observacion = request.form.get('observacion', '').strip()

    if monto <= 0:
        flash('El monto del abono debe ser mayor a $0.', 'danger')
        return redirect(url_for('providers_bp.cuenta', id=id))

    try:
        pago = ProviderPayment(
            provider_id=proveedor.id,
            monto_abonado=monto,
            observacion=observacion or None
        )
        db.session.add(pago)
        db.session.commit()
        flash(f'Abono de ${monto:,.2f} registrado para "{proveedor.nombre}".', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al registrar el abono en la base de datos.', 'danger')

    return redirect(url_for('providers_bp.cuenta', id=id))
