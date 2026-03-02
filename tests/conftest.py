"""Shared fixtures for SmartSafe tests."""
import os
import sys
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

os.environ.setdefault('ENV', 'local')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-testing')
os.environ.setdefault('FOUNDER_PASSWORD', 'test-admin-password')


@pytest.fixture(scope='session')
def app():
    """Create a Flask app instance for the full test session."""
    from src.smartsafe.api.smartsafe_saas_api import create_app
    flask_app = create_app()
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    return flask_app


@pytest.fixture
def client(app):
    """Flask test client scoped per-test."""
    with app.test_client() as c:
        yield c


@pytest.fixture
def runner(app):
    """Flask CLI test runner."""
    return app.test_cli_runner()
