"""API 级同优先配额测试：街段页改上限、分配引擎、主图数据、放不下共用同一套配额计数。"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.seed import seed_if_empty

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_if_empty(db)  # 种子：东街段优先 1 最多 2 档
    db.close()
    return TestClient(app)

def _names(payload):
    placed = {p["vendor_name"] for p in payload["placements"]}
    rejected = {r["vendor_name"]: r["reason"] for r in payload["rejected"]}
    return placed, rejected

def test_seed_quota_third_priority1_rejected(client):
    res = client.post("/api/allocate/run?segment_id=1")
    assert res.status_code == 200
    placed, rejected = _names(res.json())
    # 优先 1：阿强烧烤、林记糖水落档，第三档大碗面进放不下且原因只写配额已满
    assert {"阿强烧烤", "林记糖水"} <= placed
    assert "大碗面" not in placed
    assert rejected["大碗面"] == "配额已满"
    # 优先 2、3 不受该条限制
    assert {"老周水果", "小美饰品", "手作皮具"} <= placed
    # 巨型舞台车是空档不足，不得被改写成配额
    assert rejected["巨型舞台车"] == "无连续空档可放下且不跨越挡柱"

def test_segments_list_exposes_quotas(client):
    res = client.get("/api/segments")
    assert res.status_code == 200
    seg = [s for s in res.json() if s["name"] == "东街段"][0]
    assert seg["quotas"] == [{"priority": 1, "max_stalls": 2}]

def test_negative_quota_rejected_atomically(client):
    before = client.get("/api/segments").json()
    run_before = client.post("/api/allocate/run?segment_id=1").json()
    res = client.put("/api/segments/1/quotas", json={"quotas": [{"priority": 1, "max_stalls": -3}]})
    assert res.status_code == 400
    # 库、街段页、图、放不下全停改前，禁止半成功
    assert client.get("/api/segments").json() == before
    latest = client.get("/api/allocate/latest?segment_id=1").json()
    assert latest["id"] == run_before["id"]
    placed, rejected = _names(client.post("/api/allocate/run?segment_id=1").json())
    assert rejected["大碗面"] == "配额已满"  # 配额仍是改前的 2

def test_new_quota_applies_from_next_run(client):
    # 改前：大碗面因配额进放不下
    _, rejected1 = _names(client.post("/api/allocate/run?segment_id=1").json())
    assert rejected1["大碗面"] == "配额已满"
    # 改上限为 3 后再分：按提交瞬间新上限计数，大碗面落档
    res = client.put("/api/segments/1/quotas", json={"quotas": [{"priority": 1, "max_stalls": 3}]})
    assert res.status_code == 200
    assert res.json()["quotas"] == [{"priority": 1, "max_stalls": 3}]
    placed2, rejected2 = _names(client.post("/api/allocate/run?segment_id=1").json())
    assert "大碗面" in placed2
    assert "大碗面" not in rejected2

def test_zero_quota_means_unlimited(client):
    res = client.put("/api/segments/1/quotas", json={"quotas": [{"priority": 1, "max_stalls": 0}]})
    assert res.status_code == 200
    assert res.json()["quotas"] == []  # 0 = 不限制，不落库
    placed, _ = _names(client.post("/api/allocate/run?segment_id=1").json())
    assert "大碗面" in placed

def test_old_run_not_rewritten_by_new_quota(client):
    # 先放开配额跑出大碗面落档的旧运行
    client.put("/api/segments/1/quotas", json={"quotas": [{"priority": 1, "max_stalls": 3}]})
    run = client.post("/api/allocate/run?segment_id=1").json()
    assert "大碗面" in _names(run)[0]
    # 再收紧到 1：旧运行不得被回刷，已落摊不进放不下、不出图
    client.put("/api/segments/1/quotas", json={"quotas": [{"priority": 1, "max_stalls": 1}]})
    latest = client.get("/api/allocate/latest?segment_id=1").json()
    assert latest["id"] == run["id"]
    placed, rejected = _names(latest)
    assert "大碗面" in placed
    assert "大碗面" not in rejected
    # 新一次分配才按新上限：大碗面进放不下
    placed2, rejected2 = _names(client.post("/api/allocate/run?segment_id=1").json())
    assert "大碗面" not in placed2
    assert rejected2["大碗面"] == "配额已满"
