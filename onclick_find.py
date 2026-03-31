import re
with open('C:/Users/yaman/.gemini/antigravity/playground/ai-sales-saas/src/templates/merchant.html', encoding='utf-8') as f:
    text = f.read()
onclicks = re.findall(r'onclick="([^"]+)"', text)
for o in sorted(set(onclicks)):
    print(o)
