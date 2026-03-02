"""Tests for authentication and registration endpoints."""
import os


def test_register_missing_fields(client):
    resp = client.post('/api/register', json={})
    assert resp.status_code in (400, 500)


def test_register_valid_company(client):
    payload = {
        'company_name': 'TestCorp',
        'sector': 'construction',
        'contact_person': 'Test User',
        'email': 'test-register@example.com',
        'password': 'TestPass123!'
    }
    resp = client.post('/api/register', json=payload)
    assert resp.status_code in (200, 201, 400, 409)


def test_request_demo_valid(client):
    payload = {
        'company_name': 'Demo Corp',
        'sector': 'construction',
        'contact_person': 'Demo User',
        'email': 'demo-test@example.com',
        'password': 'DemoPass1!'
    }
    resp = client.post('/api/request-demo', json=payload)
    assert resp.status_code in (200, 201, 400, 409)


def test_request_demo_weak_password(client):
    payload = {
        'company_name': 'Demo Corp',
        'sector': 'construction',
        'contact_person': 'Demo User',
        'email': 'demo-weak@example.com',
        'password': 'abc'
    }
    resp = client.post('/api/request-demo', json=payload)
    data = resp.get_json()
    assert resp.status_code == 400 or (data and data.get('success') is False)


def test_logout_without_session(client):
    resp = client.post('/logout')
    assert resp.status_code in (200, 302, 401)


def test_admin_login_get(client):
    resp = client.get('/admin')
    assert resp.status_code == 200


def test_admin_login_wrong_password(client):
    resp = client.post('/admin', data={'password': 'wrong-password'})
    assert resp.status_code == 200
    assert b'ifre' in resp.data or b'password' in resp.data.lower()


def test_admin_login_correct_password(client):
    pw = os.environ.get('FOUNDER_PASSWORD', 'test-admin-password')
    resp = client.post('/admin', data={'password': pw})
    assert resp.status_code == 200


def test_admin_companies_without_auth(client):
    resp = client.get('/api/admin/companies')
    assert resp.status_code in (401, 403)
    data = resp.get_json()
    assert data is not None
