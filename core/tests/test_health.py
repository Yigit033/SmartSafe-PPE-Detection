"""Tests for health and core endpoints."""


def test_health_endpoint_returns_200(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    assert 'status' in data
    assert data['status'] in ('ok', 'degraded', 'error', 'healthy')


def test_health_has_timestamp(client):
    data = client.get('/health').get_json()
    assert 'timestamp' in data


def test_landing_page(client):
    resp = client.get('/')
    assert resp.status_code == 200


def test_404_returns_json(client):
    resp = client.get('/nonexistent-route-xyz')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data is not None
    assert data.get('code') == 'NOT_FOUND'
