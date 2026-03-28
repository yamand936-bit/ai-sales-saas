import ast
import json

class DictMerger(ast.NodeVisitor):
    def __init__(self):
        self.data = {"ar": {}, "en": {}, "tr": {}}
        self.current_lang = None

    def visit_Dict(self, node):
        if self.current_lang is None:
            # We are at the outer dictionary
            for key_node, value_node in zip(node.keys, node.values):
                if isinstance(key_node, ast.Constant):
                    lang = key_node.value
                    if lang in self.data:
                        self.current_lang = lang
                        self.visit(value_node)
                        self.current_lang = None
        else:
            # We are inside an inner dictionary ("ar", "en", or "tr")
            for key_node, value_node in zip(node.keys, node.values):
                if isinstance(key_node, ast.Constant) and isinstance(value_node, ast.Constant):
                    k = key_node.value
                    v = value_node.value
                    # Overwrite if duplicate inside the same block, but here it naturally merges blocks
                    self.data[self.current_lang][k] = v

merger = DictMerger()
with open('src/utils/i18n.py', 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read())
    merger.visit(tree)

# Now add the new keys
new_keys = {
    "admin_settings_title": {"ar": "إعدادات النظام - Super Admin", "en": "System Settings - Super Admin", "tr": "Sistem Ayarları - Super Admin"},
    "sys_settings_menu": {"ar": "إعدادات النظام", "en": "System Settings", "tr": "Sistem Ayarları"},
    "general_system_settings": {"ar": "إعدادات النظام العامة", "en": "General System Settings", "tr": "Genel Sistem Ayarları"},
    "update_setting": {"ar": "تحديث إعداد", "en": "Update Setting", "tr": "Ayar Güncelle"},
    "setting_key_label": {"ar": "مفتاح الإعداد (Key)", "en": "Setting Key", "tr": "Ayar Anahtarı (Key)"},
    "example_free_limit": {"ar": "مثال: free_limit", "en": "Example: free_limit", "tr": "Örnek: free_limit"},
    "update_value_label": {"ar": "تحديث القيمة (Value)", "en": "Update Value", "tr": "Değeri Güncelle (Value)"},
    "value_placeholder": {"ar": "القيمة", "en": "Value", "tr": "Değer"},
    "save_setting_btn": {"ar": "حفظ الإعداد", "en": "Save Setting", "tr": "Ayarı Kaydet"},
    "current_settings": {"ar": "الإعدادات الحالية", "en": "Current Settings", "tr": "Mevcut Ayarlar"},
    "no_settings_yet": {"ar": "لا توجد إعدادات بعد.", "en": "No settings available yet.", "tr": "Henüz ayar yok."},
    "numeric_limit_err": {"ar": "يجب أن تكون قيم الحدود أرقاماً صحيحة فقط.", "en": "Limit values must be numeric integers.", "tr": "Sınır değerleri sayısal olmalıdır."},
    "settings_saved_success": {"ar": "تم حفظ الإعدادات بنجاح", "en": "Settings saved successfully.", "tr": "Ayarlar başarıyla kaydedildi."},
    "aggregated_tokens": {"ar": "Tokens المجمعة", "en": "Aggregated Tokens", "tr": "Toplanan Jetonlar"}
}

for k, vals in new_keys.items():
    for lang, val in vals.items():
        merger.data[lang][k] = val

with open('src/utils/i18n.py', 'w', encoding='utf-8') as f:
    f.write("translations = ")
    f.write(json.dumps(merger.data, ensure_ascii=False, indent=4))
    f.write("\n\n")
    f.write("def get_t(lang: str):\n")
    f.write("    return translations.get(lang, translations['ar'])\n")
