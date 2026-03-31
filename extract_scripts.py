import re
import traceback

html = open(r'C:\Users\yaman\.gemini\antigravity\playground\ai-sales-saas\src\templates\merchant.html', 'r', encoding='utf-8', errors='ignore').read()
script_blocks = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)

for i, script in enumerate(script_blocks):
    print(f"--- Script Block {i+1} ---")
    
    # We can write it to a temp file and run 'node -c temp.js' to check syntax
    with open(f"temp_script_{i}.js", 'w', encoding='utf-8') as f:
        # replace jinja tags with valid js or remove them to prevent false positive syntax errors
        cleaned = re.sub(r'\{\{.*?\}\}', '1', script)
        cleaned = re.sub(r'\{% .*? %\}', '', cleaned)
        f.write(cleaned)

print("done")
