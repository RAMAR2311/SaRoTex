import re

path = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates\inventory\form.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('<input type="number" step="0.01" name="v_costo[]" class="form-control form-control-sm"', '<input type="text" name="v_costo[]" class="form-control form-control-sm currency-mask"')
content = content.replace('<input type="number" step="0.01" name="v_min[]" class="form-control form-control-sm"', '<input type="text" name="v_min[]" class="form-control form-control-sm currency-mask"')
content = content.replace('<input type="number" step="0.01" name="v_sug[]" class="form-control form-control-sm"', '<input type="text" name="v_sug[]" class="form-control form-control-sm currency-mask"')

# Also for the existing ones rendered by Jinja:
content = content.replace('<input type="number" step="0.01" name="v_costo[]" class="form-control form-control-sm text-secondary"', '<input type="text" name="v_costo[]" class="form-control form-control-sm text-secondary currency-mask"')
content = content.replace('<input type="number" step="0.01" name="v_min[]" class="form-control form-control-sm text-secondary"', '<input type="text" name="v_min[]" class="form-control form-control-sm text-secondary currency-mask"')
content = content.replace('<input type="number" step="0.01" name="v_sug[]" class="form-control form-control-sm fw-bold"', '<input type="text" name="v_sug[]" class="form-control form-control-sm fw-bold currency-mask"')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated inventory/form.html")
