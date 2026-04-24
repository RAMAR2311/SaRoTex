import os
import re

template_dir = r'c:\Users\Marlo\OneDrive\Documentos\sora\templates'
pattern1 = re.compile(r'"%\.[0-9]f"\|format\(([^)]+)\)')
pattern2 = re.compile(r'"\{:,\.[0-9]f\}"\.format\(([^)]+)\)')

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = pattern1.sub(r'"{:,.0f}".format(\1)', content)
            new_content = pattern2.sub(r'"{:,.0f}".format(\1)', new_content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print('Updated', path)
