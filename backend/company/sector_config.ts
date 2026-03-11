export interface PPERequirement {
    id: string;
    name: string;
    mandatory: boolean;
    priority: number;
}

export interface ComplianceSettings {
    minimum_rate: number;
    critical_ppe: string[];
}

export interface SectorPPEConfig {
    sector_id: string;
    sector_name: string;
    ppe_requirements: PPERequirement[];
    compliance_settings: ComplianceSettings;
}

export const SECTOR_PPE_CONFIGS: Record<string, SectorPPEConfig> = {
    construction: {
        sector_id: "construction",
        sector_name: "İnşaat Sektörü",
        ppe_requirements: [
            { id: "helmet", name: "Baret/Kask", mandatory: true, priority: 1 },
            { id: "safety_vest", name: "Güvenlik Yeleği", mandatory: true, priority: 2 },
            { id: "safety_shoes", name: "Güvenlik Ayakkabısı", mandatory: true, priority: 3 },
            { id: "gloves", name: "Güvenlik Eldiveni", mandatory: false, priority: 2 },
        ],
        compliance_settings: { minimum_rate: 85, critical_ppe: ["helmet", "safety_vest"] }
    },
    manufacturing: {
        sector_id: "manufacturing",
        sector_name: "İmalat Sektörü",
        ppe_requirements: [
            { id: "helmet", name: "Endüstriyel Kask", mandatory: true, priority: 1 },
            { id: "safety_vest", name: "Reflektörlü Yelek", mandatory: true, priority: 2 },
            { id: "gloves", name: "İş Eldiveni", mandatory: true, priority: 2 },
            { id: "safety_shoes", name: "Çelik Burunlu Ayakkabı", mandatory: true, priority: 3 },
        ],
        compliance_settings: { minimum_rate: 88, critical_ppe: ["helmet", "safety_shoes"] }
    },
    chemical: {
        sector_id: "chemical",
        sector_name: "Kimya Sektörü",
        ppe_requirements: [
            { id: "gloves", name: "Kimyasal Eldiven", mandatory: true, priority: 1 },
            { id: "glasses", name: "Koruyucu Gözlük", mandatory: true, priority: 1 },
            { id: "face_mask", name: "Solunum Maskesi", mandatory: true, priority: 1 },
            { id: "safety_suit", name: "Kimyasal Tulum", mandatory: true, priority: 2 },
        ],
        compliance_settings: { minimum_rate: 95, critical_ppe: ["gloves", "face_mask"] }
    },
    food: {
        sector_id: "food",
        sector_name: "Gıda Sektörü",
        ppe_requirements: [
            { id: "hairnet", name: "Bone/Başlık", mandatory: true, priority: 1 },
            { id: "face_mask", name: "Hijyen Maskesi", mandatory: true, priority: 1 },
            { id: "apron", name: "Hijyen Önlüğü", mandatory: true, priority: 2 },
            { id: "gloves", name: "Hijyen Eldiveni", mandatory: false, priority: 2 },
        ],
        compliance_settings: { minimum_rate: 90, critical_ppe: ["hairnet", "face_mask"] }
    },
    warehouse: {
        sector_id: "warehouse",
        sector_name: "Depo/Lojistik",
        ppe_requirements: [
            { id: "vest", name: "Reflektörlü Yelek", mandatory: true, priority: 1 },
            { id: "shoes", name: "Güvenlik Ayakkabısı", mandatory: true, priority: 1 },
            { id: "helmet", name: "Baret", mandatory: false, priority: 2 },
        ],
        compliance_settings: { minimum_rate: 75, critical_ppe: ["vest", "shoes"] }
    },
    energy: {
        sector_id: "energy",
        sector_name: "Enerji Sektörü",
        ppe_requirements: [
            { id: "helmet", name: "Dielektrik Baret", mandatory: true, priority: 1 },
            { id: "insulated_gloves", name: "İzole Eldiven", mandatory: true, priority: 1 },
            { id: "dielectric_boots", name: "Dielektrik Bot", mandatory: true, priority: 2 },
            { id: "safety_vest", name: "Ark Koruyucu Yelek", mandatory: true, priority: 2 },
        ],
        compliance_settings: { minimum_rate: 98, critical_ppe: ["helmet", "insulated_gloves"] }
    },
    petrochemical: {
        sector_id: "petrochemical",
        sector_name: "Petrokimya Sektörü",
        ppe_requirements: [
            { id: "helmet", name: "Antistatik Kask", mandatory: true, priority: 1 },
            { id: "gas_mask", name: "Gaz Maskesi", mandatory: true, priority: 1 },
            { id: "safety_suit", name: "Alev Almaz Tulum", mandatory: true, priority: 2 },
            { id: "gloves", name: "Kimyasal Dirençli Eldiven", mandatory: true, priority: 2 },
        ],
        compliance_settings: { minimum_rate: 97, critical_ppe: ["gas_mask", "safety_suit"] }
    },
    maritime: {
        sector_id: "maritime",
        sector_name: "Denizcilik",
        ppe_requirements: [
            { id: "life_jacket", name: "Can Yeleği", mandatory: true, priority: 1 },
            { id: "helmet", name: "Gemi Kaskı", mandatory: true, priority: 1 },
            { id: "shoes", name: "Kaymaz Gemi Botu", mandatory: true, priority: 2 },
            { id: "gloves", name: "Çalışma Eldiveni", mandatory: false, priority: 2 },
        ],
        compliance_settings: { minimum_rate: 92, critical_ppe: ["life_jacket", "helmet"] }
    },
    aviation: {
        sector_id: "aviation",
        sector_name: "Havacılık",
        ppe_requirements: [
            { id: "headset", name: "Koruyucu Kulaklık", mandatory: true, priority: 1 },
            { id: "safety_vest", name: "Yüksek Görünürlüklü Yelek", mandatory: true, priority: 1 },
            { id: "shoes", name: "Antistatik Ayakkabı", mandatory: true, priority: 2 },
            { id: "glasses", name: "UV Filtreli Gözlük", mandatory: false, priority: 2 },
        ],
        compliance_settings: { minimum_rate: 94, critical_ppe: ["headset", "safety_vest"] }
    }
};
