from datetime import datetime
import pytz

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

def obtener_hora_bogota():
    """Inyecta el uso de red horario en Colombia a nivel de sistema operativo."""
    return datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    telefono = db.Column(db.String(20)) # Nuevo Campo de Contacto (Nullable por Defecto)
    password_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(50), nullable=False, default='vendedor')
    
    ventas = db.relationship('Sale', backref='vendedor', lazy=True)
    ajustes_stock = db.relationship('StockAdjustment', backref='admin', lazy=True)
    arqueos = db.relationship('ArqueoCaja', backref='cajero', lazy=True)
    pagos_recibidos = db.relationship('StaffPayment', backref='receptor', lazy=True)

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    cantidad_stock = db.Column(db.Integer, nullable=False, default=0)
    precio_costo = db.Column(db.Numeric(10, 2), nullable=False, default=0.00) # El Costo de Bodega
    precio_minimo = db.Column(db.Numeric(10, 2), nullable=False)
    precio_sugerido = db.Column(db.Numeric(10, 2), nullable=False)
    imagen = db.Column(db.String(255), nullable=True) # Nombre de la foto subida
    observacion = db.Column(db.Text, nullable=True) # Nota descriptiva
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)
    
    detalles_venta = db.relationship('SaleDetail', backref='producto', lazy=True)
    ajustes_stock = db.relationship('StockAdjustment', backref='producto_rel', lazy=True, cascade='all, delete-orphan')
    variantes = db.relationship('ProductVariant', backref='producto_padre', lazy=True, cascade='all, delete-orphan')
    @property
    def total_stock(self):
        if self.variantes:
            return sum(v.cantidad_stock for v in self.variantes)
        return self.cantidad_stock

    @property
    def rango_precios(self):
        if not self.variantes:
            return None
        precios = [v.precio_sugerido for v in self.variantes if v.precio_sugerido is not None]
        if not precios:
            return None
        min_p = min(precios)
        max_p = max(precios)
        if min_p == max_p:
            return min_p
        return (min_p, max_p)

    @property
    def rango_costos(self):
        if not self.variantes:
            return None
        precios = [v.precio_costo for v in self.variantes if v.precio_costo is not None]
        if not precios:
            return None
        min_p = min(precios)
        max_p = max(precios)
        if min_p == max_p:
            return min_p
        return (min_p, max_p)

    @property
    def rango_minimos(self):
        if not self.variantes:
            return None
        precios = [v.precio_minimo for v in self.variantes if v.precio_minimo is not None]
        if not precios:
            return None
        min_p = min(precios)
        max_p = max(precios)
        if min_p == max_p:
            return min_p
        return (min_p, max_p)

# ===================== VARIANTES DE PRODUCTO (Subcategorías: Color, Talla, etc.) =====================

class ProductVariant(db.Model):
    __tablename__ = 'product_variants'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    nombre_variante = db.Column(db.String(100), nullable=False)  # Ej: "Rojo - Talla M"
    sku_variante = db.Column(db.String(50), unique=True, nullable=True, index=True)
    cantidad_stock = db.Column(db.Integer, nullable=False, default=0)
    precio_costo = db.Column(db.Numeric(10, 2), nullable=True)     # Override o hereda del padre
    precio_minimo = db.Column(db.Numeric(10, 2), nullable=True)
    precio_sugerido = db.Column(db.Numeric(10, 2), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)


# ===================== MODELO DE VENTAS AMPLIADO (POS Terminal) =====================

class Sale(db.Model):
    __tablename__ = 'sales'
    
    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha_venta = db.Column(db.DateTime, default=obtener_hora_bogota)
    monto_total = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    costo_total = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)   # Suma de costos de los items
    utilidad = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)       # Ganancia = monto_total - costo_total
    metodo_pago = db.Column(db.String(50), nullable=False, default='efectivo') # Mantiene compatibilidad legacy
    estado = db.Column(db.String(30), nullable=False, default='completada')    # completada, anulada, etc.
    
    detalles = db.relationship('SaleDetail', backref='venta', lazy=True, cascade="all, delete-orphan")
    pagos = db.relationship('SalePayment', backref='venta', lazy=True, cascade="all, delete-orphan")

class SaleDetail(db.Model):
    __tablename__ = 'sale_details'
    
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)  # NULL si es producto externo
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)  # NULL si es producto simple
    cantidad_vendida = db.Column(db.Integer, nullable=False)
    precio_venta_final = db.Column(db.Numeric(10, 2), nullable=False)
    costo_unitario = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    es_externo = db.Column(db.Boolean, nullable=False, default=False)    # True = producto manual/prestado
    nombre_externo = db.Column(db.String(200), nullable=True)            # Nombre del producto fantasma

    variante = db.relationship('ProductVariant', backref='detalles_venta', lazy=True)


class SalePayment(db.Model):
    """Consolidación Multimétodo — Un recibo puede tener N métodos de pago."""
    __tablename__ = 'sale_payments'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)  # efectivo, nequi, bancolombia, binance, tarjeta
    monto = db.Column(db.Numeric(10, 2), nullable=False)


class StockAdjustment(db.Model):
    __tablename__ = 'stock_adjustments'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_movimiento = db.Column(db.String(100), nullable=True) # Ej: Creación Inicial, Ajuste Manual
    stock_anterior = db.Column(db.Integer, nullable=False)
    stock_nuevo = db.Column(db.Integer, nullable=False)
    fecha_ajuste = db.Column(db.DateTime, default=obtener_hora_bogota)

class ArqueoCaja(db.Model):
    __tablename__ = 'arqueo_caja'
    
    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha_arqueo = db.Column(db.Date, nullable=False)
    base_inicial = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    gastos_del_dia = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    observaciones_gastos = db.Column(db.String(255), nullable=True)
    total_efectivo_sistema = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    total_nequi_sistema = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    total_daviplata_sistema = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    total_bancolombia_sistema = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

class Maneo(db.Model):
    __tablename__ = 'maneos'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    local_vecino = db.Column(db.String(150), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(50), nullable=False, default='PENDIENTE') # PENDIENTE, FACTURADO, DEVUELTO
    fecha_prestamo = db.Column(db.DateTime, default=obtener_hora_bogota)
    fecha_resolucion = db.Column(db.DateTime, nullable=True)

    producto = db.relationship('Product', backref='maneos', lazy=True)
    variante = db.relationship('ProductVariant', backref='maneos_rel', lazy=True)

class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_gasto = db.Column(db.String(50), nullable=False) # 'Gasto Diario' o 'Costo Indirecto'
    categoria = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False, default='efectivo')
    fecha_gasto = db.Column(db.DateTime, default=obtener_hora_bogota)

    usuario = db.relationship('User', backref='gastos', lazy=True)


# ===================== MÓDULO DE PROVEEDORES (Cuentas por Pagar) =====================

class Provider(db.Model):
    __tablename__ = 'providers'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    telefono = db.Column(db.String(20), nullable=True)
    empresa = db.Column(db.String(200), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

    invoices = db.relationship('ProviderInvoice', backref='proveedor', lazy=True, cascade='all, delete-orphan')
    pagos = db.relationship('ProviderPayment', backref='proveedor', lazy=True, cascade='all, delete-orphan')

class ProviderInvoice(db.Model):
    __tablename__ = 'provider_invoices'

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False)
    numero_factura = db.Column(db.String(100), nullable=True) # Opcional
    monto_total = db.Column(db.Numeric(10, 2), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    comprobante = db.Column(db.String(255), nullable=True) # Foto o PDF adjunto
    fecha_factura = db.Column(db.DateTime, default=obtener_hora_bogota)

class ProviderDelivery(db.Model):
    __tablename__ = 'provider_deliveries'
    # ... conservado por ahora por histórico ...

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    cantidad_entregada = db.Column(db.Integer, nullable=False)
    costo_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    costo_total = db.Column(db.Numeric(10, 2), nullable=False)
    fecha_entrega = db.Column(db.DateTime, default=obtener_hora_bogota)

    producto = db.relationship('Product', backref='entregas_proveedor', lazy=True)

class ProviderPayment(db.Model):
    __tablename__ = 'provider_payments'

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False)
    monto_abonado = db.Column(db.Numeric(10, 2), nullable=False)
    observacion = db.Column(db.String(255), nullable=True)
    fecha_pago = db.Column(db.DateTime, default=obtener_hora_bogota)


# ===================== MÓDULO DE PAGOS AL PERSONAL =====================

class StaffPayment(db.Model):
    __tablename__ = 'staff_payments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    observacion = db.Column(db.String(255), nullable=True)
    fecha_pago = db.Column(db.DateTime, default=obtener_hora_bogota)
