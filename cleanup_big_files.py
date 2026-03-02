
import os
import re

def extract_and_cleanup():
    target_file = r'c:\Users\Lenovo\Desktop\smart-safe\backend\src\smartsafe\api\smartsafe_saas_api.py'
    template_dir = r'c:\Users\Lenovo\Desktop\smart-safe\frontend\src\templates'
    
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)

    with open(target_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Outline sonucuna göre güncel satır aralıkları
    tasks = [
        (5796, 5917, "get_admin_template", "admin.html"),
        (5695, 5794, "get_admin_login_template", "admin_login.html"),
        (5267, 5693, "get_login_template", "login.html"),
        (3718, 5265, "get_dashboard_template", "dashboard.html"),
        (2228, 3716, "get_home_template", "home.html"),
        (1982, 2226, "get_pricing_template", "pricing.html")
    ]

    # İndekslerin kaymaması için tersten (aşağıdan yukarıya) işlem yapıyoruz
    tasks.sort(key=lambda x: x[0], reverse=True)

    for start, end, method_name, filename in tasks:
        # Satırları çek (start ve end 1-based index)
        block_lines = lines[start-1:end]
        block_text = "".join(block_lines)
        
        # HTML kısmını return ''' ... ''' arasından çekmeye çalış
        content_match = re.search(r"return\s+'''\s*(.*?)'''", block_text, re.DOTALL)
        if content_match:
            html_content = content_match.group(1).strip()
        else:
            # Fallback: döküman stringi ve return satırını atla, geri kalanı al
            html_content = "".join(block_lines[2:-1]).strip()

        # HTML dosyasını oluştur
        with open(os.path.join(template_dir, filename), 'w', encoding='utf-8') as f_html:
            f_html.write(html_content)
        
        # Python tarafındaki metodu güncelle
        replacement = f"""    def {method_name}(self{', company_id' if 'login' in method_name and 'admin' not in method_name else ''}{', error=None' if 'admin_login' in method_name else ''}):
        \"\"\"Dış dosyadan yüklenen {filename} template\"\"\"
        try:
            with open('frontend/src/templates/{filename}', 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"<h1>Error</h1><p>{{e}}</p>"
"""
        lines[start-1:end] = [replacement + "\n"]
        print(f"✅ {method_name} -> {filename} dosyasına taşındı ve Python kodu temizlendi.")

    with open(target_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)

if __name__ == "__main__":
    extract_and_cleanup()
