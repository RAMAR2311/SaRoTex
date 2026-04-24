import os

# 1. Fix inventory/form.html
path1 = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates\inventory\form.html'
with open(path1, 'r', encoding='utf-8') as f:
    c1 = f.read()

c1 = c1.replace('<input type="number" step="0.01" class="form-control bg-light border-0" name="precio_minimo"',
                '<input type="text" class="currency-mask form-control bg-light border-0" name="precio_minimo"')

c1 = c1.replace('<input type="number" step="0.01" class="form-control bg-light border-0" name="precio_sugerido"',
                '<input type="text" class="currency-mask form-control bg-light border-0" name="precio_sugerido"')

with open(path1, 'w', encoding='utf-8') as f:
    f.write(c1)

# 2. Fix inventory/modal_variantes.html
path2 = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates\inventory\modal_variantes.html'
with open(path2, 'r', encoding='utf-8') as f:
    c2 = f.read()

c2 = c2.replace('<input type="number" step="1" name="precio_minimo" class="form-control border-start-0 ps-0"',
                '<input type="text" name="precio_minimo" class="currency-mask form-control border-start-0 ps-0"')

c2 = c2.replace('<input type="number" step="1" name="precio_sugerido" class="form-control border-start-0 ps-0 border-pink border-1"',
                '<input type="text" name="precio_sugerido" class="currency-mask form-control border-start-0 ps-0 border-pink border-1"')

c2 = c2.replace('<input type="number" step="1" name="precio_minimo" class="form-control border-start-0 ps-0 text-secondary"',
                '<input type="text" name="precio_minimo" class="currency-mask form-control border-start-0 ps-0 text-secondary"')

c2 = c2.replace('<input type="number" step="1" name="precio_sugerido" class="form-control border-start-0 ps-0 fw-bold"',
                '<input type="text" name="precio_sugerido" class="currency-mask form-control border-start-0 ps-0 fw-bold"')

with open(path2, 'w', encoding='utf-8') as f:
    f.write(c2)

print("Fixes applied successfully.")
