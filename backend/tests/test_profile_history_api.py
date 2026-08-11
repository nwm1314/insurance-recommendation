import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + os.path.join(tempfile.gettempdir(), 'insurance_profile_history_pytest.db').replace(os.sep, '/'),
)
os.environ.setdefault('DISABLE_SCHEDULER_IN_TESTS', 'true')

try:
    os.remove(os.path.join(tempfile.gettempdir(), 'insurance_profile_history_pytest.db'))
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


def _register(client, email, password='Password12345'):
    resp = client.post('/api/auth/register', json={'email': email, 'password': password, 'full_name': email})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _login(client, email, password='Password12345'):
    resp = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert resp.status_code == 200, resp.text
    token = client.cookies.get('access_token')
    assert token is not None
    client.cookies.clear()
    return {'Authorization': f'Bearer {token}'}


def _full_profile():
    return {
        'age': 35,
        'gender': 'male',
        'annual_income': 300000,
        'job_class': 2,
        'life_stage': 'married_with_kids',
        'family_burden': 'dual',
        'health_status': 'standard',
        'health_issues': [],
        'existing_coverage': ['social'],
        'budget_ratio': 0.08,
        'preferred_companies': ['众安保险'],
        'enable_llm_engine': False,
    }


def test_profile_and_history_require_auth(client):
    client.cookies.clear()
    assert client.get('/api/my/profiles').status_code == 401
    assert client.post('/api/my/profiles', json={'name': 'x', 'profile': {}}).status_code == 401
    assert client.get('/api/my/profiles/1').status_code == 401
    assert client.put('/api/my/profiles/1', json={'name': 'x', 'profile': {}}).status_code == 401
    assert client.delete('/api/my/profiles/1').status_code == 401
    assert client.get('/api/my/recommendations').status_code == 401
    assert client.get('/api/my/recommendations/1').status_code == 401
    assert client.post('/api/my/recommendations', json={'profile': {}, 'result': {}}).status_code == 401
    assert client.delete('/api/my/recommendations/1').status_code == 401


def test_profile_crud_flow_and_ownership_isolation(client):
    _register(client, 'profile-owner@example.com')
    h1 = _login(client, 'profile-owner@example.com')

    resp = client.post('/api/my/profiles', headers=h1, json={
        'name': '2026方案', 'note': '家庭保障',
        'profile': _full_profile(),
    })
    assert resp.status_code == 200, resp.text
    pid = resp.json()['id']

    detail = client.get(f'/api/my/profiles/{pid}', headers=h1)
    assert detail.status_code == 200, detail.text
    assert detail.json()['name'] == '2026方案'
    assert detail.json()['note'] == '家庭保障'
    assert detail.json()['profile']['annual_income'] == 300000

    lst = client.get('/api/my/profiles', headers=h1)
    assert lst.status_code == 200, lst.text
    assert [p['id'] for p in lst.json()['profiles']] == [pid]

    updated_profile = _full_profile()
    updated_profile['age'] = 40
    updated_profile['annual_income'] = 500000
    updated_profile['enable_llm_engine'] = True
    updated_profile['health_issues'] = ['hypertension_l1']
    upd = client.put(f'/api/my/profiles/{pid}', headers=h1, json={
        'name': '2026家庭升级版', 'note': '更新备注',
        'profile': updated_profile,
    })
    assert upd.status_code == 200, upd.text
    assert upd.json()['name'] == '2026家庭升级版'
    assert upd.json()['profile']['enable_llm_engine'] is True
    assert upd.json()['profile']['health_issues'] == ['hypertension_l1']

    _register(client, 'profile-intruder@example.com')
    h2 = _login(client, 'profile-intruder@example.com')
    assert client.get(f'/api/my/profiles/{pid}', headers=h2).status_code == 404
    assert client.put(f'/api/my/profiles/{pid}', headers=h2, json={'name': 'hack', 'profile': {}}).status_code == 404
    assert client.delete(f'/api/my/profiles/{pid}', headers=h2).status_code == 404

    owner_list = client.get('/api/my/profiles', headers=h2)
    assert owner_list.status_code == 200
    assert len(owner_list.json()['profiles']) == 0

    assert client.delete(f'/api/my/profiles/{pid}', headers=h1).status_code == 200
    gone = client.get(f'/api/my/profiles/{pid}', headers=h1)
    assert gone.status_code == 404
    assert '?' not in gone.json().get('detail', '')


def test_recommendation_history_ownership_isolation(client):
    _register(client, 'rec-owner@example.com')
    h1 = _login(client, 'rec-owner@example.com')

    saved = client.post('/api/my/recommendations', headers=h1, json={
        'profile': _full_profile(),
        'result': {'engine_mode': 'rule', 'packages': [], 'disclaimer': 'x'},
    })
    assert saved.status_code == 200, saved.text
    rid = saved.json()['id']

    detail = client.get(f'/api/my/recommendations/{rid}', headers=h1)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body['profile']['annual_income'] == 300000
    assert body['result']['engine_mode'] == 'rule'

    _register(client, 'rec-intruder@example.com')
    h2 = _login(client, 'rec-intruder@example.com')
    intruder = client.get(f'/api/my/recommendations/{rid}', headers=h2)
    assert intruder.status_code == 404

    missing = client.get('/api/my/recommendations/999999', headers=h1)
    assert missing.status_code == 404
    assert '?' not in missing.json().get('detail', '')

    owner_list = client.get('/api/my/recommendations', headers=h2)
    assert owner_list.status_code == 200
    assert len(owner_list.json()['records']) == 0

    assert client.delete(f'/api/my/recommendations/{rid}', headers=h1).status_code == 200
    assert client.get(f'/api/my/recommendations/{rid}', headers=h1).status_code == 404
