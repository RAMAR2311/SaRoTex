import re

path = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates\sales\nueva.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# POS parsing fix
content = content.replace("parseFloat(document.getElementById('ext_costo').value)", "parseCurrencyStr(document.getElementById('ext_costo').value)")
content = content.replace("parseFloat(document.getElementById('ext_precio').value)", "parseCurrencyStr(document.getElementById('ext_precio').value)")
content = content.replace("parseFloat(entry.querySelector('.pago-monto').value)", "parseCurrencyStr(entry.querySelector('.pago-monto').value)")
content = content.replace("parseFloat(inp.value)", "parseCurrencyStr(inp.value)")
content = content.replace("parseInt(valor)", "parseCurrencyStr(valor)")
content = content.replace("parseFloat(valor)", "parseCurrencyStr(valor)")

# One specific fix: in 'actualizarItem(index, campo, valor)' for the 'cantidad' field it's safe to use parseCurrencyStr (will return integer since no decimal allowed in input pattern) but let's make sure:
# actually cantidad is not a currency-mask, but parseCurrencyStr safely removes commas if any exist.

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("POS JS Updated.")
