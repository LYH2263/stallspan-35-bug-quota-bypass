from app.services.first_fit_engine import allocate_first_fit, free_spans_from_pillars

def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}])
    assert len(spans) == 3
    assert spans[0][0] == 0.0

def test_first_fit_no_cross_pillar():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 12.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert any(p.vendor_name == "A" for p in r.placements)
    # 12m may fit in a free span after first placement depending on remainders
    assert len(r.placements) + len(r.rejected) == 2

def test_reject_oversized():
    vendors = [{"id": 1, "name": "Huge", "stall_width_m": 25.0, "priority": 1}]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"

def test_quota_full_rejects_even_when_gap_fits():
    # 优先 1 上限 2：第三档优先 1 空档够宽也必须进放不下，原因只写配额已满
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 3.0, "priority": 1},
        {"id": 3, "name": "C", "stall_width_m": 6.0, "priority": 1},
    ]
    r = allocate_first_fit(30.0, vendors, [], {1: 2})
    assert [p.vendor_name for p in r.placements] == ["A", "B"]
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "C"
    assert r.rejected[0].reason == "配额已满"

def test_quota_short_circuits_cross_pillar():
    # 同一摊既跨柱放不进、又超配额：主因只保留配额已满，不得并句
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "Huge", "stall_width_m": 25.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars, {1: 1})
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"
    assert r.rejected[0].reason == "配额已满"

def test_quota_per_priority_independent():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 4.0, "priority": 2},
        {"id": 3, "name": "C", "stall_width_m": 4.0, "priority": 2},
    ]
    r = allocate_first_fit(30.0, vendors, [], {1: 1, 2: 1})
    assert {p.vendor_name for p in r.placements} == {"A", "B"}
    assert [x.vendor_name for x in r.rejected] == ["C"]
    assert r.rejected[0].reason == "配额已满"

def test_quota_zero_or_missing_means_unlimited():
    vendors = [{"id": i, "name": f"V{i}", "stall_width_m": 2.0, "priority": 1} for i in range(1, 5)]
    assert len(allocate_first_fit(30.0, vendors, [], {1: 0}).placements) == 4
    assert len(allocate_first_fit(30.0, vendors, [], None).placements) == 4
    assert len(allocate_first_fit(30.0, vendors, []).placements) == 4

def test_quota_counts_only_placed_stalls():
    # 优先 1 第一档本身放不下（不占配额），第二档优先 1 仍可用掉名额
    vendors = [
        {"id": 1, "name": "TooBig", "stall_width_m": 25.0, "priority": 1},
        {"id": 2, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 3, "name": "B", "stall_width_m": 4.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars, {1: 1})
    assert [p.vendor_name for p in r.placements] == ["A"]
    reasons = {x.vendor_name: x.reason for x in r.rejected}
    assert reasons["TooBig"] == "无连续空档可放下且不跨越挡柱"
    assert reasons["B"] == "配额已满"
