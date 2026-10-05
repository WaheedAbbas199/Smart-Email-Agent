from fastapi import APIRouter, Depends

from app.api.deps import get_email_service
from app.api.schemas import EmailOut
from app.services.email_service import EmailService

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(svc: EmailService = Depends(get_email_service)):
    data = svc.dashboard()
    to_out = lambda rows: [EmailOut.model_validate(e) for e in rows]
    return {
        "stats": data["stats"],
        "recent_important": to_out(data["recent_important"]),
        "action_required": to_out(data["action_required"]),
        "upcoming_deadlines": to_out(data["upcoming_deadlines"]),
    }
