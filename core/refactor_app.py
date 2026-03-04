
import re
import os

file_path = r'c:\Users\Lenovo\Desktop\smart-safe\core\app.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Refaktör edilecek fonksiyonlar ve yeni gövdeleri
refactors = {
    'get_pricing_template': '        """Pricing page template\"\"\"\n        return render_template(\'pricing.html\')',
    'get_home_template': '        """Home page template\"\"\"\n        return render_template(\'home.html\')',
    'get_dashboard_template': '        """Advanced Dashboard Template with Real-time PPE Analytics\"\"\"\n        return render_template(\'dashboard.html\', **kwargs)',
    'get_login_template': '        """Company login page template\"\"\"\n        return render_template(\'login.html\', company_id=company_id)',
    'get_admin_login_template': '        """Admin login template\"\"\"\n        return render_template(\'admin_login.html\', error=error)',
    'get_admin_template': '        """Professional Admin Panel Template for Company Management\"\"\"\n        return render_template(\'admin.html\', **kwargs)',
    'get_company_settings_template': '        """Advanced Company Settings Template\"\"\"\n        return render_template(\'company_settings.html\', **kwargs)',
    'get_users_template': '        """Company Users Management Template\"\"\"\n        return render_template(\'users.html\', **kwargs)',
    'get_reports_template': '        """Company Reports Template\"\"\"\n        return render_template(\'reports.html\', **kwargs)',
    'get_camera_management_template': '        """Advanced Camera Management Template with Discovery and Testing\"\"\"\n        return render_template(\'camera_management.html\', **kwargs)'
}

for func_name, new_body in refactors.items():
    # Bu regex, fonksiyon tanımını ve sonrasındaki devasa string bloğunu yakalar
    # Not: get_live_detection_template'e dokunmamak için adları tam eşleştiriyoruz
    pattern = rf'def {func_name}\(self,?.*?\):.*?(?=\n\s+def |\n\s+# |\n\s+SmartSafeSaaSAPI|\Z)'
    
    # Argümanları korumak için fonksiyon imzasını yakalayalım
    if func_name == 'get_login_template':
        replacement = f'def {func_name}(self, company_id):\n{new_body}'
    elif func_name == 'get_admin_login_template':
        replacement = f'def {func_name}(self, error=None):\n{new_body}'
    elif func_name == 'get_dashboard_template':
        replacement = f'def {func_name}(self, **kwargs):\n{new_body}'
    else:
        replacement = f'def {func_name}(self):\n{new_body}'
        
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ app.py (Dashboard ve diğerleri dahil) başarıyla refaktör edildi.")
