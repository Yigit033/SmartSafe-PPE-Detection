#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix UTF-8 encoding issues in index.html
"""

import os

# Encoding fix mappings
FIXES = {
    'Ã§': 'ç',
    'Ã¼': 'ü',
    'ÅŸ': 'ş',
    'Ä±': 'ı',
    'Ã¶': 'ö',
    'ÄŸ': 'ğ',
    'Ã‡': 'Ç',
    'Ãœ': 'Ü',
    'Åž': 'Ş',
    'Ä°': 'İ',
    'Ã–': 'Ö',
    'Äž': 'Ğ',
    'Å': 'Ş',  # Tek başına Å karakteri
    'Ä': 'İ',  # Tek başına Ä karakteri
    'â€™': "'",
    'â€œ': '"',
    'â€': '"',
    'â€"': '—',
    'â€"': '–',
    'â€¢': '•',
    'Ã¼st': 'üst',
    'Ã¶zel': 'özel',
    'Ã§ok': 'çok',
    'iÅŸ': 'iş',
    'gÃ¼': 'gü',
    'EndÃ¼striyel': 'Endüstriyel',
    'GÃ¼ven': 'Güven',
    'gÃ¼venilir': 'güvenilir',
    'TÃ¼rkÃ§e': 'Türkçe',
    'GeliÅŸmiÅŸ': 'Gelişmiş',
    'Ã¶ÄŸrenme': 'öğrenme',
    'GerÃ§ek': 'Gerçek',
    'ZamanlÄ±': 'Zamanlı',
    'YÃ¼ksek': 'Yüksek',
    'DoÄŸruluk': 'Doğruluk',
    'SÃ¼rekli': 'Sürekli',
    'Ã–ÄŸrenme': 'Öğrenme',
    'AkÄ±llÄ±': 'Akıllı',
    'Ä°leri': 'İleri',
    'DavranÄ±ÅŸ': 'Davranış',
    'BakÄ±m': 'Bakım',
    'iÅŸ akÄ±ÅŸlarÄ±': 'iş akışları',
    'Ã‡oklu': 'Çoklu',
    'DesteÄŸi': 'Desteği',
    'eÅŸ': 'eş',
    'zamanlÄ±': 'zamanlı',
    'Ä°zleme': 'İzleme',
    'YÃ¼k': 'Yük',
    'UyarÄ±': 'Uyarı',
    'AnlÄ±k': 'Anlık',
    'Ã¶zelleÅŸtirilebilir': 'özelleştirilebilir',
    'uyarÄ±': 'uyarı',
    'mekanizmasÄ±': 'mekanizması',
    'DetaylÄ±': 'Detaylı',
    'Ã–zelleÅŸtirilebilir': 'Özelleştirilebilir',
    'DesteÄŸi': 'Desteği',
    'Ã–zel': 'Özel',
    'altyapÄ±sÄ±': 'altyapısı',
    'Ã§Ã¶zÃ¼mler': 'çözümler',
    'Ã‡Ã¶zÃ¼mleri': 'Çözümleri',
    'YapÄ±landÄ±rma': 'Yapılandırma',
    'bakÄ±m': 'bakım',
    'CanlÄ±': 'Canlı',
    'MÃ¼dahale': 'Müdahale',
    'GÃ¼venlik': 'Güvenlik',
    'standartlarÄ±': 'standartları',
    'Åifreleme': 'Şifreleme',
    'TabanlÄ±': 'Tabanlı',
    'EriÅŸim': 'Erişim',
    'KullanÄ±cÄ±': 'Kullanıcı',
    'YÃ¶netimi': 'Yönetimi',
    'kontrolÃ¼': 'kontrolü',
    'Ã‡ok': 'Çok',
    'LoglarÄ±': 'Logları',
}

def fix_encoding(file_path):
    """Fix encoding issues in the file"""
    print(f"Reading file: {file_path}")
    
    # Read file with UTF-8 encoding
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Apply all fixes
    for wrong, correct in FIXES.items():
        if wrong in content:
            count = content.count(wrong)
            print(f"Fixing: '{wrong}' -> '{correct}' ({count} occurrences)")
            content = content.replace(wrong, correct)
    
    # Write back with UTF-8 encoding
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n✅ File fixed successfully!")
        print(f"Total changes made: {len([k for k in FIXES.keys() if k in original_content])}")
    else:
        print("\n✅ No encoding issues found!")

if __name__ == '__main__':
    file_path = 'index.html'
    if os.path.exists(file_path):
        fix_encoding(file_path)
    else:
        print(f"❌ File not found: {file_path}")
