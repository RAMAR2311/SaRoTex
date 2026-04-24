import re

path = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates\sales\nueva.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Static HTML replacements
content = content.replace('>$0.00<', '>$0<')
content = content.replace("'$0.00'", "'$0'")
content = content.replace('step="0.01"', 'step="1"')
content = content.replace('placeholder="0.00"', 'placeholder="0"')

# 2. Inject JS helper
if 'function formatCOP' not in content:
    content = content.replace('<script>\n', '<script>\n    function formatCOP(amount) {\n        return Math.round(amount).toLocaleString("en-US");\n    }\n')

# 3. Input value replacement (no commas allowed in type="number")
content = content.replace('value="${item.precio_final.toFixed(2)}"', 'value="${Math.round(item.precio_final)}"')

# 4. Display replacements using formatCOP
content = content.replace('.toFixed(2)', '') # Just strip the .toFixed(2) in JS?
# Wait, if I just strip .toFixed(2), then `$${subtotal}` becomes `$1000`. It won't have commas!
# Let's replace specifically:
content = re.sub(r'\$\{([^}]+)\.toFixed\(2\)\}', r'${formatCOP(\1)}', content)

# 5. Let's do regex replacements manually for known patterns in nueva.html
content = content.replace('formatCOP(item.precio_final)', 'Math.round(item.precio_final)') # Revert the input value if it was matched
content = content.replace('${nuevoPrecio.toFixed(2)}', '${formatCOP(nuevoPrecio)}')
content = content.replace('${item.precio_limite.toFixed(2)}', '${formatCOP(item.precio_limite)}')
content = content.replace('${subtotal.toFixed(2)}', '${formatCOP(subtotal)}')
content = content.replace('${granTotal.toFixed(2)}', '${formatCOP(granTotal)}')
content = content.replace('${(granTotal - costoTotal).toFixed(2)}', '${formatCOP(granTotal - costoTotal)}')
content = content.replace('${costoTotal.toFixed(2)}', '${formatCOP(costoTotal)}')
content = content.replace('${diferencia.toFixed(2)}', '${formatCOP(diferencia)}')
content = content.replace('${Math.abs(diferencia).toFixed(2)}', '${formatCOP(Math.abs(diferencia))}')
content = content.replace('${dif.toFixed(2)}', '${formatCOP(dif)}')
content = content.replace('${parseFloat(data.total).toFixed(2)}', '${formatCOP(parseFloat(data.total))}')

# Re-run for general remaining .toFixed(2)
content = re.sub(r'\$\{([a-zA-Z0-9_.\-\(\) ]+)\.toFixed\(2\)\}', r'${formatCOP(\1)}', content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Pos HTML updated!")
