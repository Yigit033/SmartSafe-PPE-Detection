
import os
import shutil
import re

class FrontendGenerator:
    def __init__(self):
        # Yollar
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_dir = os.path.join(self.base_dir, 'templates')
        self.output_dir = os.path.join(self.base_dir, 'output')
        
        # Eğer varsa projenin genel statik dosyaları (logo, css vb.)
        # Bu yollar projenin yapısına göre güncellenebilir
        self.static_source = os.path.join(self.base_dir, 'output', 'static') # Mevcut static'i korumak için

    def clear_output(self):
        """Build öncesi temizlik yapar."""
        if os.path.exists(self.output_dir):
            print("🧹 Eski 'output' klasörü temizleniyor...")
            # Sadece HTML'leri temizleyelim, static klasörüne dokunmayalım (şimdilik)
            for item in os.listdir(self.output_dir):
                item_path = os.path.join(self.output_dir, item)
                if os.path.isfile(item_path) and item.endswith('.html'):
                    os.remove(item_path)

    def generate_static_site(self):
        """Templates içindeki tüm HTML dosyalarını render edip output'a taşır."""
        print("🚀 Gelişmiş Frontend Generation Başladı...")
        self.clear_output()
        
        if not os.path.exists(self.template_dir):
            print(f"❌ HATA: {self.template_dir} bulunamadı!")
            return

        templates = [f for f in os.listdir(self.template_dir) if f.endswith('.html')]
        
        for template_name in templates:
            source_path = os.path.join(self.template_dir, template_name)
            output_path = os.path.join(self.output_dir, template_name)
            
            with open(source_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Gelişmiş render (Placeholder'lar, lang="tr" kontrolleri vb.)
            final_content = self.render_static_content(content, template_name)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            print(f"✅ {template_name} -> rendered.")

        # index.html oluştur
        self.create_index()

        print("\n🎉 Build Tamamlandı! Tüm dosyalar 'frontend/output' altında hazır.")

    def create_index(self):
        """landing.html'i index.html olarak ayarlar."""
        landing = os.path.join(self.output_dir, 'landing.html')
        index = os.path.join(self.output_dir, 'index.html')
        if os.path.exists(landing):
            shutil.copy2(landing, index)
            print("✨ landing.html -> index.html olarak kopyalandı.")

    def render_static_content(self, content, name):
        """Jinja2 placeholder'larını temizler ve dili optimize eder."""
        # {{ ... }} bloklarını temizle
        content = re.sub(r'\{\{.*?\}\}', '', content)
        # {% ... %} bloklarını temizle
        content = re.sub(r'\{%.*?%\}', '', content)
        
        # Dil kontrolü (User kuralına göre: uppercase varsa lang=tr ekle)
        if 'uppercase' in content.lower() and 'lang="tr"' not in content.lower():
            content = content.replace('<html', '<html lang="tr"')
            
        return content

if __name__ == "__main__":
    generator = FrontendGenerator()
    generator.generate_static_site()
