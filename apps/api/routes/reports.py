from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.database.session import get_db
from apps.api.security.auth import require_admin
from apps.api.services import compliance_report

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/compliance")
def compliance(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """PDF summary of print activity between two dates (inclusive). Defaults
    to the last 7 days. Counts and categories only, never detected values."""
    today = datetime.utcnow().date()
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=6)
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="The start date is after the end date.")
    if (date_to - date_from).days > 366:
        raise HTTPException(status_code=400, detail="Choose a period of one year or less.")

    data = compliance_report.collect(db, date_from, date_to, get_settings().organisation_name)
    pdf = compliance_report.render_pdf(data)
    filename = f"SecurePrint_compliance_{date_from.isoformat()}_to_{date_to.isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
