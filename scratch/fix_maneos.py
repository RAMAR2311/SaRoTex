import os

path = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates\admin\maneos.html'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # The line has: min="{{ "{:,.0f}".format(m.producto.precio_minimo) }}"
    # We want to replace type="number" step="0.01" ... name="precio_venta"
    content = content.replace(
        '<input type="number" step="0.01" min="{{ "{:,.0f}".format(m.producto.precio_minimo) }}" class="form-control bg-light border-0" name="precio_venta"',
        '<input type="text" class="currency-mask form-control bg-light border-0" name="precio_venta"'
    )
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

print("maneos.html updated")
