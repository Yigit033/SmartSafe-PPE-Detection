# SmartSafe AI - PPE Detection System

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- OpenCV
- YOLOv8
- Flask

### Installation
```bash
pip install -r requirements.txt
```

### Database Setup
```bash
# Database is automatically initialized when the application starts
# All migrations are handled by database_adapter.py

# Run integration tests to verify all sectors
python test_sector_integration.py
```

### Start the Application
```bash
python smartsafe_saas_api.py
```

## 📊 Supported Sectors

SmartSafe AI supports **9 sectors** with specialized PPE detection:

### Core Sectors
- **Construction (İnşaat)** - Hard hat, safety vest, safety shoes
- **Chemical (Kimya)** - Chemical suit, respirator, safety glasses
- **Food (Gıda)** - Hair net, gloves, apron
- **Manufacturing (İmalat)** - Safety helmet, work gloves, safety shoes
- **Warehouse (Depo/Lojistik)** - Safety vest, safety shoes, helmet

### Advanced Sectors
- **Energy (Enerji)** - Insulated gloves, dielectric boots, arc flash suit
- **Petrochemical (Petrokimya)** - Fire-resistant suit, gas detector, safety helmet
- **Marine (Denizcilik & Tersane)** - Life jacket, safety helmet, work boots
- **Aviation (Havacılık)** - High-visibility vest, safety helmet, safety shoes

## 🔧 Database Management

### Automatic Migration
- `database_adapter.py` - Handles all database migrations automatically
- `test_sector_integration.py` - Comprehensive testing for all sector integrations

### Usage
```bash
# Database migrations are automatic - no manual steps needed
# Run integration tests
python test_sector_integration.py
```

## 🌐 API Endpoints

### Core Detection
- `POST /analyze_construction_ppe` - Construction sector PPE analysis
- `POST /analyze_chemical_ppe` - Chemical sector PPE analysis
- `POST /analyze_food_ppe` - Food sector PPE analysis
- `POST /analyze_manufacturing_ppe` - Manufacturing sector PPE analysis
- `POST /analyze_warehouse_ppe` - Warehouse sector PPE analysis

### Advanced Sectors
- `POST /analyze_energy_ppe` - Energy sector PPE analysis
- `POST /analyze_petrochemical_ppe` - Petrochemical sector PPE analysis
- `POST /analyze_marine_ppe` - Marine sector PPE analysis
- `POST /analyze_aviation_ppe` - Aviation sector PPE analysis

## 🏗️ Architecture

### Core Components
- `smartsafe_saas_api.py` - Main Flask application with API endpoints
- `smartsafe_sector_manager.py` - Sector configuration management
- `smartsafe_sector_detector_factory.py` - Sector-specific detector factory
- `database_adapter.py` - Database connection and schema management (includes automatic migrations)

### Sector Integration
Each sector has:
- **Mandatory PPE**: Critical safety equipment required by law
- **Optional PPE**: Additional safety equipment for enhanced protection
- **Detection Settings**: Confidence thresholds and detection intervals
- **Penalty Settings**: Violation penalties and escalation rules
- **Compliance Requirements**: Minimum compliance rates and reporting

## 📈 Performance

- **Real-time Detection**: 30 FPS processing capability
- **Multi-Camera Support**: Up to 25 cameras per company
- **Sector-Specific Models**: Optimized detection for each industry
- **Compliance Tracking**: Automated violation detection and reporting

## 🔒 Security

- **Session Management**: Secure company session validation
- **API Key Authentication**: Unique keys for each company
- **Data Encryption**: Secure storage of sensitive information
- **Access Control**: Role-based permissions and restrictions

## 🚀 Deployment

### Local Development (SQLite)
```bash
python smartsafe_saas_api.py
```

### Production (PostgreSQL/Render.com)
```bash
# Database migrations are automatic
# Start with Gunicorn
gunicorn -w 4 -b 0.0.0.0:10000 smartsafe_saas_api:app
```

## 📝 Testing

### Run All Tests
```bash
python test_sector_integration.py
```

### Test Coverage
- ✅ All 9 sectors supported
- ✅ Database schema compatibility (SQLite/PostgreSQL)
- ✅ Sector detector creation
- ✅ PPE configuration validation
- ✅ Detection settings verification
- ✅ Penalty configuration testing
- ✅ Compliance requirements validation

## 🤝 Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Check the [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- Review [REAL_CAMERA_DEPLOYMENT_GUIDE.md](REAL_CAMERA_DEPLOYMENT_GUIDE.md)
- Contact the development team

---

**SmartSafe AI** - Professional PPE Detection for All Industries