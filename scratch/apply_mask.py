import os
import re

template_dir = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates'

pattern_input = re.compile(r'(<input[^>]+type=[\'\"]number[\'\"][^>]+name=[\'\"][^\'\"]*(?:precio|costo|monto|base_inicial|v_costo|v_min|v_sug)[\^\'\"]*[\'\"][^>]*>)', re.IGNORECASE)

def replace_input(match):
    tag = match.group(1)
    
    # We also need to match id or class if name isn't there, e.g. pago-monto in POS
    if 'ext_cantidad' in tag or 'cantidad' in tag or 'stock' in tag:
        return tag # ignore quantity fields
        
    tag = tag.replace('type="number"', 'type="text"').replace("type='number'", "type='text'")
    tag = tag.replace('step="1"', '').replace("step='1'", "")
    tag = tag.replace('step="0.01"', '').replace("step='0.01'", "")
    
    if 'class="' in tag:
        tag = tag.replace('class="', 'class="currency-mask ')
    elif "class='" in tag:
        tag = tag.replace("class='", "class='currency-mask ")
    else:
        tag = tag.replace('<input ', '<input class="currency-mask" ')
        
    return tag

# Second pass for inputs with ID instead of name (like in POS)
pattern_id = re.compile(r'(<input[^>]+type=[\'\"]number[\'\"][^>]+id=[\'\"](?:ext_costo|ext_precio|gastos_del_dia)[\'\"][^>]*>)', re.IGNORECASE)
pattern_class = re.compile(r'(<input[^>]+type=[\'\"]number[\'\"][^>]+class=[\'\"][^\'\"]*pago-monto[^\'\"]*[\'\"][^>]*>)', re.IGNORECASE)

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = pattern_input.sub(replace_input, content)
            new_content = pattern_id.sub(replace_input, new_content)
            new_content = pattern_class.sub(replace_input, new_content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print('Updated', path)
