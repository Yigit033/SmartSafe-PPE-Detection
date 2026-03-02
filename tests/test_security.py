"""Security-focused tests for SmartSafe API."""
import os


def test_no_hardcoded_founder_password():
    """FOUNDER_PASSWORD must not be hardcoded in source."""
    api_path = os.path.join(
        os.path.dirname(__file__), '..', 'src', 'smartsafe', 'api', 'smartsafe_saas_api.py'
    )
    with open(api_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'smartsafe2024admin' not in content, "Hardcoded admin password found in source"


def test_no_hardcoded_secret_key():
    """SECRET_KEY must not have a predictable fallback."""
    api_path = os.path.join(
        os.path.dirname(__file__), '..', 'src', 'smartsafe', 'api', 'smartsafe_saas_api.py'
    )
    with open(api_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'smartsafe-saas-2024-secure-key' not in content


def test_no_hardcoded_production_key():
    """Production config must not have a predictable SECRET_KEY."""
    cfg_path = os.path.join(
        os.path.dirname(__file__), '..', 'production_config.py'
    )
    with open(cfg_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'smartsafe-production-key-change-in-production' not in content


def test_env_example_exists():
    """.env.example should exist for onboarding."""
    env_example = os.path.join(os.path.dirname(__file__), '..', '.env.example')
    assert os.path.isfile(env_example), ".env.example file is missing"


def test_env_example_has_required_vars():
    env_example = os.path.join(os.path.dirname(__file__), '..', '.env.example')
    with open(env_example, 'r') as f:
        content = f.read()
    for var in ['SECRET_KEY', 'FOUNDER_PASSWORD', 'DATABASE_URL', 'SENDGRID_API_KEY']:
        assert var in content, f".env.example missing {var}"


def test_camera_api_requires_auth(client):
    """Camera endpoints must require authentication."""
    resp = client.get('/api/company/fake-id/cameras')
    assert resp.status_code in (401, 403)


def test_dvr_api_requires_auth(client):
    resp = client.get('/api/company/fake-id/dvr/list')
    assert resp.status_code in (401, 403)


def test_detection_api_requires_auth(client):
    resp = client.get('/api/company/fake-id/sh17/sectors')
    assert resp.status_code in (401, 403)


def test_alerts_api_requires_auth(client):
    resp = client.get('/api/company/fake-id/alerts')
    assert resp.status_code in (401, 403)


def test_subscription_api_requires_auth(client):
    resp = client.get('/api/company/fake-id/subscription')
    assert resp.status_code in (401, 403)
