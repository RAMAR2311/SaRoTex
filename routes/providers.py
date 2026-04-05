from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Provider, ProviderInvoice, ProviderPayment, Product, StockAdjustment
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
    """Vista de cuenta individual del proveedor con saldo pendiente basado en facturas."""
    proveedor = Provider.query.get_or_404(id)

    # Calcular totales históricos de Facturas y Abonos
    total_facturas = sum(f.monto_total for f in proveedor.invoices) or 0
    total_abonos = sum(p.monto_abonado for p in proveedor.pagos) or 0
    saldo_pendiente = float(total_facturas) - float(total_abonos)

    # Invoices and Payments sorted by date
    historial = sorted(
        [{'tipo': 'Factura', 'monto': float(f.monto_total), 'fecha': f.fecha_factura, 'ref': f.numero_factura or 'N/A', 'desc': f.descripcion} for f in proveedor.invoices] +
        [{'tipo': 'Abono', 'monto': float(p.monto_abonado), 'fecha': p.fecha_pago, 'ref': 'N/A', 'desc': p.observacion} for p in proveedor.pagos],
        key=lambda x: x['fecha'] or datetime.min,
        reverse=True
    )

    return render_template(
        'providers/cuenta.html',
        proveedor=proveedor,
        total_facturas=float(total_facturas),
        total_abonos=float(total_abonos),
        saldo_pendiente=saldo_pendiente,
        historial=historial
    )


@providers_bp.route('/<int:id>/invoice', methods=['POST'])
@login_required
@admin_required
def registrar_factura(id):
    """Registra una factura de proveedor (valor monetario)."""
    proveedor = Provider.query.get_or_404(id)

    monto_total = request.form.get('monto_total', type=float)
    numero_factura = request.form.get('numero_factura', '').strip()
    descripcion = request.form.get('descripcion', '').strip()

    if not monto_total or monto_total <= 0:
        flash('El monto de la factura debe ser mayor a $0.', 'danger')
        return redirect(url_for('providers_bp.cuenta', id=id))

    try:
        nueva_factura = ProviderInvoice(
            provider_id=proveedor.id,
            monto_total=monto_total,
            numero_factura=numero_factura or None,
            descripcion=descripcion or None
        )
        db.session.add(nueva_factura)
        db.session.commit()
        flash(f'Factura de ${monto_total:,.2f} registrada para "{proveedor.nombre}".', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al registrar la factura en la base de datos.', 'danger')

    return redirect(url_for('providers_bp.cuenta', id=id))


@providers_bp.route('/<int:id>/payment', methods=['POST'])
@login_required
@admin_required
def registrar_pago(id):
    """Registra un abono o pago al proveedor."""
    proveedor = Provider.query.get_or_404(id)

    monto = request.form.get('monto_abonado', type=float)
    observacion = request.form.get('observacion', '').strip()

    if not monto or monto <= 0:
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
