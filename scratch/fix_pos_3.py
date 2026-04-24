import re

path = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates\sales\nueva.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix missing formatCOP in JS variables
content = content.replace('${subtotal}', '${formatCOP(subtotal)}')
content = content.replace('totalAmountEl.innerText = `$${granTotal}`;', 'totalAmountEl.innerText = `$${formatCOP(granTotal)}`;')

# 2. Fix dynamic input to use type="text" and class="currency-mask"
content = content.replace(
    '<input type="number" step="1" class="form-control text-end border-0 bg-light"',
    '<input type="text" class="form-control text-end border-0 bg-light currency-mask"'
)
content = content.replace(
    'value="${Math.round(item.precio_final)}"',
    'value="${formatCOP(item.precio_final)}"'
)

# 3. Remove Utilidad and Costo from HTML
# Costo Estimado
content = re.sub(r'<span>Costo Estimado: <strong id="status_cost">.*?</strong></span>', '', content)
# Utilidad Estimada block
content = re.sub(r'<div class="d-flex justify-content-between mb-4">\s*<span class="text-muted small">Utilidad Estimada:</span>\s*<span class="fw-bold small" id="utilidad_estimada".*?</span>\s*</div>', '', content)

# 4. Remove JS references to avoid null errors
content = content.replace("const utilidadEl = document.getElementById('utilidad_estimada');", "")
content = content.replace("utilidadEl.innerText = '$0';", "")
content = content.replace("utilidadEl.innerText = `$${(granTotal - costoTotal)}`;", "")
content = content.replace("document.getElementById('status_cost').innerText = `$${costoTotal}`;", "")

# 5. Fix any missed formatCOP for multi-pago indicators
content = content.replace("Faltan: $${diferencia}`", "Faltan: $${formatCOP(diferencia)}`")
content = content.replace("Excedente: $${Math.abs(diferencia)}`", "Excedente: $${formatCOP(Math.abs(diferencia))}`")
content = content.replace("Diferencia: $${dif}.", "Diferencia: $${formatCOP(dif)}.")
content = content.replace("Total: $${parseFloat(data.total)}", "Total: $${formatCOP(parseFloat(data.total))}")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("POS fixes applied.")
