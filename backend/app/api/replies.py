from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_reply_service
from app.api.schemas import DraftOut, DraftUpdate, SendRequest
from app.integrations.provider import EmailProviderError
from app.services.reply_service import ReplyError, ReplyService

router = APIRouter(prefix="/api/replies", tags=["replies"])


def _nf():
    return HTTPException(404, {"code": "not_found", "message": "Draft not found"})


@router.get("")
def list_replies(status: str | None = Query(None, max_length=20), svc: ReplyService = Depends(get_reply_service)):
    return {"items": [DraftOut.model_validate(d).model_dump(mode="json", exclude={"email": {"body"}})
                      for d in svc.drafts.list(status)]}


@router.patch("/{reply_id}", response_model=DraftOut)
def edit(reply_id: int, body: DraftUpdate, svc: ReplyService = Depends(get_reply_service)):
    try:
        return svc.edit(reply_id, body.body)
    except LookupError:
        raise _nf()
    except ReplyError as exc:
        raise HTTPException(409, {"code": "reply_conflict", "message": str(exc)})


@router.post("/{reply_id}/approve", response_model=DraftOut)
def approve(reply_id: int, svc: ReplyService = Depends(get_reply_service)):
    try:
        return svc.approve(reply_id)
    except LookupError:
        raise _nf()
    except ReplyError as exc:
        raise HTTPException(409, {"code": "reply_conflict", "message": str(exc)})


@router.post("/{reply_id}/reject", response_model=DraftOut)
def reject(reply_id: int, svc: ReplyService = Depends(get_reply_service)):
    try:
        return svc.reject(reply_id)
    except LookupError:
        raise _nf()
    except ReplyError as exc:
        raise HTTPException(409, {"code": "reply_conflict", "message": str(exc)})


@router.post("/{reply_id}/send", response_model=DraftOut)
def send(reply_id: int, body: SendRequest, svc: ReplyService = Depends(get_reply_service)):
    try:
        return svc.send(reply_id, body.confirm)
    except LookupError:
        raise _nf()
    except ReplyError as exc:
        raise HTTPException(409, {"code": "reply_conflict", "message": str(exc)})
    except EmailProviderError as exc:
        raise HTTPException(502, {"code": "send_failed", "message": str(exc)})
