from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Segment, SegmentQuota
router = APIRouter(prefix="/segments", tags=["segments"])

class QuotaIn(BaseModel):
    priority: int
    max_stalls: int  # 0 = 不限制

class QuotasIn(BaseModel):
    quotas: list[QuotaIn]

def _quota_rows(db: Session, segment_id: int) -> list[dict]:
    rows = db.scalars(select(SegmentQuota).where(SegmentQuota.segment_id == segment_id)
                      .order_by(SegmentQuota.priority)).all()
    return [{"priority": q.priority, "max_stalls": q.max_stalls} for q in rows]

@router.get("")
def list_segments(db: Session = Depends(get_db)):
    segs = db.scalars(select(Segment).order_by(Segment.id)).all()
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name, "width_m": r.width_m,
             "quotas": _quota_rows(db, r.id)} for r in segs]

@router.put("/{segment_id}/quotas")
def put_quotas(segment_id: int, payload: QuotasIn, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    # 先整体校验：任一非法上限（负数）即拒绝，库与页面全部停在改前，不允许半成功
    for q in payload.quotas:
        if q.max_stalls < 0:
            raise HTTPException(400, "配额上限不能为负数")
        if q.priority < 1:
            raise HTTPException(400, "优先级必须为正整数")
    merged: dict[int, int] = {}
    for q in payload.quotas:
        merged[q.priority] = q.max_stalls
    db.execute(delete(SegmentQuota).where(SegmentQuota.segment_id == segment_id))
    for priority, max_stalls in merged.items():
        if max_stalls > 0:  # 0 / 留空 = 不限制，不落库
            db.add(SegmentQuota(segment_id=segment_id, priority=priority, max_stalls=max_stalls))
    db.commit()
    return {"id": seg.id, "name": seg.name, "quotas": _quota_rows(db, segment_id)}
