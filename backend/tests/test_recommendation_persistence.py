import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + os.path.join(tempfile.gettempdir(), 'insurance_rec_pytest.db').replace(os.sep, '/'),
)
os.environ.setdefault('DISABLE_SCHEDULER_IN_TESTS', 'true')

try:
    os.remove(os.path.join(tempfile.gettempdir(), 'insurance_rec_pytest.db'))
except OSError:
    pass

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.app.database import SessionLocal
from backend.app.models.auth import AuditLog, RecommendationRecord, RefreshToken, SavedProfile, User, UserRole


@pytest.fixture(scope='session')
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_data():
    db = SessionLocal()
    try:
        db.query(AuditLog).delete()
        db.query(RecommendationRecord).delete()
        db.query(SavedProfile).delete()
        db.query(RefreshToken).delete()
        db.query(UserRole).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
    yield


def _register(client, email='rec-test@example.com', password='Password12345'):
    resp = client.post('/api/auth/register', json={'email': email, 'password': password, 'full_name': email})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_save_and_list_recommendation(client):
    admin = _register(client)
    client.post('/api/auth/login', json={'email': 'rec-test@example.com', 'password': 'Password12345'})
    access_token = client.cookies.get('access_token')
    headers = {'Authorization': f'Bearer {access_token}'}

    save_resp = client.post('/api/my/recommendations', headers=headers, json={
        'profile': {'age': 30, 'gender': 'male'},
        'result': {'packages': [], 'engine_mode': 'rule'},
    })
    assert save_resp.status_code == 200, save_resp.text
    assert save_resp.json()['id'] is not None

    list_resp = client.get('/api/my/recommendations', headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    records = list_resp.json()['records']
    assert len(records) == 1
    assert records[0]['profile']['age'] == 30
    assert records[0]['result']['engine_mode'] == 'rule'


def test_save_recommendation_requires_auth(client):
    resp = client.post('/api/my/recommendations', json={'profile': {}, 'result': {}})
    assert resp.status_code == 401
