#!/usr/bin/env python3
"""
Sector-Specific PPE Mapping System
Maps generic PPE detections to sector-specific equipment
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class SectorPPERule:
    """Sektör özel PPE kuralı"""
    sector: str
    ppe_type: str
    base_class: str          # Temel model sınıfı
    sector_class: str        # Sektör özel sınıf
    is_required: bool        # Zorunlu mu?
    confidence_threshold: float = 0.3
    description: str = ""

class SectorPPEMapper:
    """Sektörel PPE Haritalama Sistemi"""
    
    def __init__(self):
        self.sector_rules = self.initialize_sector_rules()
        self.ppe_descriptions = self.load_ppe_descriptions()
    
    def initialize_sector_rules(self) -> Dict[str, List[SectorPPERule]]:
        """Sektör kurallarını başlat"""
        rules = {
            'construction': [
                SectorPPERule('construction', 'helmet', 'helmet', 'construction_helmet', True, 0.3, 'İnşaat kaskı'),
                SectorPPERule('construction', 'safety_vest', 'safety_vest', 'high_visibility_vest', True, 0.3, 'Yüksek görünürlük yeleği'),
                SectorPPERule('construction', 'safety_shoes', 'safety_shoes', 'steel_toe_boots', True, 0.3, 'Çelik burunlu bot'),
                SectorPPERule('construction', 'gloves', 'gloves', 'work_gloves', False, 0.3, 'İş eldiveni'),
                SectorPPERule('construction', 'glasses', 'glasses', 'safety_glasses', False, 0.3, 'Güvenlik gözlüğü'),
            ],
            'chemical': [
                SectorPPERule('chemical', 'face_mask', 'face_mask', 'chemical_respirator', True, 0.3, 'Kimyasal solunum maskesi'),
                SectorPPERule('chemical', 'gloves', 'gloves', 'chemical_gloves', True, 0.3, 'Kimyasal eldiven'),
                SectorPPERule('chemical', 'safety_vest', 'safety_vest', 'chemical_suit', True, 0.3, 'Kimyasal tulum'),
                SectorPPERule('chemical', 'glasses', 'glasses', 'chemical_goggles', True, 0.3, 'Kimyasal gözlük'),
                SectorPPERule('chemical', 'safety_shoes', 'safety_shoes', 'chemical_boots', False, 0.3, 'Kimyasal bot'),
            ],
            'food': [
                SectorPPERule('food', 'helmet', 'helmet', 'hair_net', True, 0.3, 'Bone/Başlık'),
                SectorPPERule('food', 'face_mask', 'face_mask', 'hygiene_mask', True, 0.3, 'Hijyen maskesi'),
                SectorPPERule('food', 'safety_vest', 'safety_vest', 'hygiene_apron', True, 0.3, 'Hijyen önlüğü'),
                SectorPPERule('food', 'gloves', 'gloves', 'hygiene_gloves', False, 0.3, 'Hijyen eldiveni'),
                SectorPPERule('food', 'safety_shoes', 'safety_shoes', 'non_slip_shoes', False, 0.3, 'Kaymaz ayakkabı'),
            ],
            'manufacturing': [
                SectorPPERule('manufacturing', 'helmet', 'helmet', 'industrial_helmet', True, 0.3, 'Endüstriyel kask'),
                SectorPPERule('manufacturing', 'safety_vest', 'safety_vest', 'reflective_vest', True, 0.3, 'Reflektörlü yelek'),
                SectorPPERule('manufacturing', 'gloves', 'gloves', 'industrial_gloves', True, 0.3, 'Endüstriyel eldiven'),
                SectorPPERule('manufacturing', 'safety_shoes', 'safety_shoes', 'steel_toe_shoes', True, 0.3, 'Çelik burunlu ayakkabı'),
                SectorPPERule('manufacturing', 'glasses', 'glasses', 'safety_glasses', False, 0.3, 'Güvenlik gözlüğü'),
            ],
            'warehouse': [
                SectorPPERule('warehouse', 'safety_vest', 'safety_vest', 'visibility_vest', True, 0.3, 'Görünürlük yeleği'),
                SectorPPERule('warehouse', 'safety_shoes', 'safety_shoes', 'warehouse_shoes', True, 0.3, 'Depo ayakkabısı'),
                SectorPPERule('warehouse', 'helmet', 'helmet', 'protective_helmet', False, 0.3, 'Koruyucu kask'),
                SectorPPERule('warehouse', 'gloves', 'gloves', 'warehouse_gloves', False, 0.3, 'Depo eldiveni'),
            ],
            'general': [
                SectorPPERule('general', 'helmet', 'helmet', 'safety_helmet', True, 0.3, 'Güvenlik kaskı'),
                SectorPPERule('general', 'safety_vest', 'safety_vest', 'safety_vest', True, 0.3, 'Güvenlik yeleği'),
                SectorPPERule('general', 'gloves', 'gloves', 'safety_gloves', False, 0.3, 'Güvenlik eldiveni'),
                SectorPPERule('general', 'safety_shoes', 'safety_shoes', 'safety_shoes', False, 0.3, 'Güvenlik ayakkabısı'),
                SectorPPERule('general', 'glasses', 'glasses', 'safety_glasses', False, 0.3, 'Güvenlik gözlüğü'),
            ],
            # Yeni Sektörler
            'energy': [
                SectorPPERule('energy', 'helmet', 'helmet', 'dielectric_helmet', True, 0.3, 'Dielektrik Baret'),
                SectorPPERule('energy', 'gloves', 'gloves', 'insulated_gloves', True, 0.3, 'Yalıtımlı Eldiven'),
                SectorPPERule('energy', 'safety_vest', 'safety_vest', 'arc_flash_suit', True, 0.3, 'Ark Flash Koruyucu Giysi'),
                SectorPPERule('energy', 'safety_shoes', 'safety_shoes', 'insulated_boots', True, 0.3, 'Yalıtımlı Ayakkabı'),
                SectorPPERule('energy', 'glasses', 'glasses', 'arc_flash_visor', True, 0.3, 'Ark Flash Vizör'),
            ],
            'petrochemical': [
                SectorPPERule('petrochemical', 'helmet', 'helmet', 'chem_helmet', True, 0.3, 'Kimyasal Dayanımlı Baret'),
                SectorPPERule('petrochemical', 'face_mask', 'face_mask', 'gas_mask', True, 0.3, 'Gaz Maskesi'),
                SectorPPERule('petrochemical', 'safety_vest', 'safety_vest', 'chemical_suit', True, 0.3, 'Kimyasal Koruyucu Tulum'),
                SectorPPERule('petrochemical', 'gloves', 'gloves', 'chemical_resistant_gloves', True, 0.3, 'Kimyasal Eldiven'),
                SectorPPERule('petrochemical', 'safety_shoes', 'safety_shoes', 'chemical_boots', True, 0.3, 'Kimyasal Dayanımlı Bot'),
            ],
            'shipyard': [
                SectorPPERule('shipyard', 'helmet', 'helmet', 'marine_helmet', True, 0.3, 'Denizcilik Bareti'),
                SectorPPERule('shipyard', 'safety_vest', 'safety_vest', 'life_vest', True, 0.3, 'Can Yeleği'),
                SectorPPERule('shipyard', 'gloves', 'gloves', 'waterproof_gloves', True, 0.3, 'Su Geçirmez Eldiven'),
                SectorPPERule('shipyard', 'safety_shoes', 'safety_shoes', 'marine_boots', True, 0.3, 'Denizcilik Botu'),
                SectorPPERule('shipyard', 'harness', 'harness', 'fall_protection', True, 0.3, 'Yüksekte Çalışma Kemeri'),
            ],
            'aviation': [
                SectorPPERule('aviation', 'helmet', 'helmet', 'aviation_helmet', True, 0.3, 'Havacılık Bareti'),
                SectorPPERule('aviation', 'safety_vest', 'safety_vest', 'high_vis_vest', True, 0.3, 'Yüksek Görünürlük Yeleği'),
                SectorPPERule('aviation', 'ear_protection', 'ear_protection', 'aviation_headset', True, 0.3, 'Gürültü Önleyici Kulaklık'),
                SectorPPERule('aviation', 'safety_shoes', 'safety_shoes', 'esd_shoes', True, 0.3, 'Anti-statik Ayakkabı'),
                SectorPPERule('aviation', 'gloves', 'gloves', 'mechanic_gloves', True, 0.3, 'Mekanik Eldiven'),
            ],
        }
        return rules
    
    def load_ppe_descriptions(self) -> Dict[str, str]:
        """PPE açıklamalarını yükle"""
        return {
            # Construction
            'construction_helmet': 'İnşaat Kaskı - Düşen nesnelerden koruma',
            'high_visibility_vest': 'Yüksek Görünürlük Yeleği - Görünürlük artırma',
            'steel_toe_boots': 'Çelik Burunlu Bot - Ayak koruma',
            'work_gloves': 'İş Eldiveni - El koruma',
            'safety_glasses': 'Güvenlik Gözlüğü - Göz koruma',
            
            # Chemical
            'chemical_respirator': 'Kimyasal Solunum Maskesi - Solunum yolu koruma',
            'chemical_gloves': 'Kimyasal Eldiven - Kimyasal madde koruması',
            'chemical_suit': 'Kimyasal Tulum - Tam vücut koruma',
            'chemical_goggles': 'Kimyasal Gözlük - Kimyasal sıçrama koruması',
            'chemical_boots': 'Kimyasal Bot - Ayak kimyasal koruması',
            
            # Food
            'hair_net': 'Bone/Başlık - Saç hijyeni',
            'hygiene_mask': 'Hijyen Maskesi - Gıda hijyeni',
            'hygiene_apron': 'Hijyen Önlüğü - Gıda güvenliği',
            'hygiene_gloves': 'Hijyen Eldiveni - El hijyeni',
            'non_slip_shoes': 'Kaymaz Ayakkabı - Kayma önleme',
            
            # Manufacturing
            'industrial_helmet': 'Endüstriyel Kask - Endüstriyel koruma',
            'reflective_vest': 'Reflektörlü Yelek - Görünürlük ve koruma',
            'industrial_gloves': 'Endüstriyel Eldiven - Makine koruması',
            'steel_toe_shoes': 'Çelik Burunlu Ayakkabı - Endüstriyel ayak koruma',
            
            # Warehouse
            'visibility_vest': 'Görünürlük Yeleği - Depo görünürlüğü',
            'warehouse_shoes': 'Depo Ayakkabısı - Depo güvenliği',
            'protective_helmet': 'Koruyucu Kask - Genel koruma',
            'warehouse_gloves': 'Depo Eldiveni - Malzeme taşıma',
        }
    
    def get_sector_rules(self, sector: str) -> List[SectorPPERule]:
        """Sektör kurallarını getir"""
        return self.sector_rules.get(sector, self.sector_rules['general'])
    
    def get_required_ppe(self, sector: str) -> List[str]:
        """Sektör için zorunlu PPE'leri getir"""
        rules = self.get_sector_rules(sector)
        return [rule.sector_class for rule in rules if rule.is_required]
    
    def get_optional_ppe(self, sector: str) -> List[str]:
        """Sektör için opsiyonel PPE'leri getir"""
        rules = self.get_sector_rules(sector)
        return [rule.sector_class for rule in rules if not rule.is_required]
    
    def map_base_to_sector(self, base_class: str, sector: str) -> Optional[str]:
        """Temel sınıfı sektörel sınıfa çevir"""
        rules = self.get_sector_rules(sector)
        for rule in rules:
            if rule.base_class == base_class:
                return rule.sector_class
        return base_class  # Eşleşme yoksa orijinal sınıfı döndür
    
    def get_ppe_description(self, sector_class: str) -> str:
        """PPE açıklamasını getir"""
        return self.ppe_descriptions.get(sector_class, sector_class)
    
    def validate_company_ppe_config(self, company_ppe: List[str], sector: str) -> Dict[str, any]:
        """Şirket PPE konfigürasyonunu doğrula"""
        sector_rules = self.get_sector_rules(sector)
        available_ppe = [rule.sector_class for rule in sector_rules]
        
        valid_ppe = []
        invalid_ppe = []
        
        for ppe in company_ppe:
            # Temel sınıftan sektörel sınıfa çevir
            sector_ppe = self.map_base_to_sector(ppe, sector)
            
            if sector_ppe in available_ppe:
                valid_ppe.append(sector_ppe)
            else:
                invalid_ppe.append(ppe)
        
        return {
            'valid_ppe': valid_ppe,
            'invalid_ppe': invalid_ppe,
            'is_valid': len(invalid_ppe) == 0,
            'recommendations': self.get_required_ppe(sector)
        }
    
    def generate_sector_ppe_options(self, sector: str) -> Dict[str, List[Dict[str, str]]]:
        """Sektör için PPE seçeneklerini oluştur"""
        rules = self.get_sector_rules(sector)
        
        required_options = []
        optional_options = []
        
        for rule in rules:
            option = {
                'value': rule.base_class,
                'label': rule.description,
                'sector_class': rule.sector_class,
                'description': self.get_ppe_description(rule.sector_class)
            }
            
            if rule.is_required:
                required_options.append(option)
            else:
                optional_options.append(option)
        
        return {
            'required': required_options,
            'optional': optional_options
        }
    
    def create_detection_mapping(self, sector: str) -> Dict[str, str]:
        """Detection için mapping tablosu oluştur"""
        rules = self.get_sector_rules(sector)
        mapping = {}
        
        for rule in rules:
            mapping[rule.base_class] = rule.sector_class
        
        return mapping
    
    def save_mapping_config(self, file_path: str):
        """Mapping konfigürasyonunu kaydet"""
        config = {
            'sector_rules': {},
            'ppe_descriptions': self.ppe_descriptions
        }
        
        for sector, rules in self.sector_rules.items():
            config['sector_rules'][sector] = []
            for rule in rules:
                config['sector_rules'][sector].append({
                    'ppe_type': rule.ppe_type,
                    'base_class': rule.base_class,
                    'sector_class': rule.sector_class,
                    'is_required': rule.is_required,
                    'confidence_threshold': rule.confidence_threshold,
                    'description': rule.description
                })
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Mapping config saved: {file_path}")
    
    def load_mapping_config(self, file_path: str):
        """Mapping konfigürasyonunu yükle"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self.ppe_descriptions = config.get('ppe_descriptions', {})
            
            # Kuralları yeniden oluştur
            sector_rules = {}
            for sector, rules_data in config.get('sector_rules', {}).items():
                sector_rules[sector] = []
                for rule_data in rules_data:
                    rule = SectorPPERule(
                        sector=sector,
                        ppe_type=rule_data['ppe_type'],
                        base_class=rule_data['base_class'],
                        sector_class=rule_data['sector_class'],
                        is_required=rule_data['is_required'],
                        confidence_threshold=rule_data.get('confidence_threshold', 0.3),
                        description=rule_data.get('description', '')
                    )
                    sector_rules[sector].append(rule)
            
            self.sector_rules = sector_rules
            logger.info(f"✅ Mapping config loaded: {file_path}")
            
        except Exception as e:
            logger.error(f"❌ Config loading failed: {e}")

# Test fonksiyonu
def test_sector_mapper():
    """Sector mapper test"""
    mapper = SectorPPEMapper()
    
    # Test all sectors
    sectors = ['construction', 'chemical', 'food', 'manufacturing', 'warehouse']
    
    for sector in sectors:
        print(f"\n🏭 {sector.upper()} SECTOR:")
        
        required = mapper.get_required_ppe(sector)
        optional = mapper.get_optional_ppe(sector)
        
        print(f"  Required PPE: {required}")
        print(f"  Optional PPE: {optional}")
        
        # Test mapping
        base_classes = ['helmet', 'safety_vest', 'gloves', 'face_mask']
        print(f"  Base → Sector Mapping:")
        for base in base_classes:
            sector_class = mapper.map_base_to_sector(base, sector)
            print(f"    {base} → {sector_class}")
    
    # Save config
    mapper.save_mapping_config('configs/sector_ppe_mapping.json')
    print(f"\n✅ Config saved to: configs/sector_ppe_mapping.json")

if __name__ == "__main__":
    test_sector_mapper() 