import re

path = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates\sales\nueva.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace all `$0.00` placeholders in HTML with `$0`
content = content.replace('>$0.00<', '>$0<')
content = content.replace("'$0.00'", "'$0'")

# 2. Replace step="0.01" placeholder="0.00" with step="1" placeholder="0"
content = content.replace('step="0.01"', 'step="1"')
content = content.replace('placeholder="0.00"', 'placeholder="0"')

# 3. Inject JS format function after <script> tag
if 'function formatCOP' not in content:
    content = content.replace('<script>\n', '<script>\n    function formatCOP(amount) {\n        return Math.round(amount).toLocaleString("en-US");\n    }\n')

# 4. Replace `.toFixed(2)` with `formatCOP(...)` in JS templates and messages
# Need to be careful with string interpolation: ${...toFixed(2)} -> ${formatCOP(...)}
content = re.sub(r'\$\{([^}]+)\.toFixed\(2\)\}', r'${formatCOP(\1)}', content)

# 5. Handle `alert(...toFixed(2))`
content = re.sub(r'\$([^$]+)\.toFixed\(2\)', r'$formatCOP(\1)', content) # Wait, the alert was `parseFloat(data.total).toFixed(2)` inside `${}` which was already caught by 4.

# 6. Any stray `.toFixed(2)` without `${}` but concatenated?
# e.g. .value = item.precio_final.toFixed(2)
content = content.replace('.toFixed(2)', '') # Just in case? No, wait.
# Actually, for input values, we don't want formatCOP because inputs of type "number" don't accept commas!
# `<input ... value="${item.precio_final.toFixed(2)}"` 
# if I run step 4: `<input ... value="${formatCOP(item.precio_final)}"` -> This will BREAK the input type="number" because of the comma!
