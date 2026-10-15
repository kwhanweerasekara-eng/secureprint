from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.database.session import get_db
from apps.api.models.audit import AuditEvent
from apps.api.models.enums import AuditEventType, PrinterStatus
from apps.api.models.printer import Printer
from apps.api.models.user import User
from apps.api.schemas.printer import PrinterCreate, PrinterOut, PrinterTestResult
from apps.api.security.auth import get_current_active_user, require_admin
from apps.api.services import printing
from apps.api.services.engine_loader import audit_service

router = APIRouter(prefix="/api/v1/printers", tags=["printers"])


@router.get("", response_model=list[PrinterOut])
def list_printers(db: Session = Depends(get_db), _user: User = Depends(get_current_active_user)):
    """Any authenticated user can list printers - staff need this to pick a
    printer when releasing a sanitized document. Only admins may manage them."""
    return db.query(Printer).order_by(Printer.name).all()


@router.post("", response_model=PrinterOut, status_code=201)
def create_printer(payload: PrinterCreate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    printer = Printer(**payload.model_dump())
    db.add(printer)
    db.commit()
    db.refresh(printer)
    return printer


@router.post("/{printer_id}/test", response_model=PrinterTestResult)
def test_printer_connection(printer_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Actually opens a connection to the printer over the network - IPP
    Get-Printer-Attributes, or a raw TCP connect for AppSocket printers - and
    records the real result. No agent, no simulated response."""
    printer = db.get(Printer, printer_id)
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    result = printing.test_printer(printer.protocol.value, printer.host, printer.port, printer.ipp_path, printer.use_tls)

    printer.status = PrinterStatus.ONLINE if result.ok else PrinterStatus.OFFLINE
    printer.last_tested_at = datetime.utcnow()
    printer.last_test_message = result.message
    db.commit()

    audit_service.record_event(
        db,
        AuditEvent,
        event_type=AuditEventType.PRINTER_TESTED.value,
        user_id=admin.id,
        message=f"Tested printer '{printer.name}': {result.message}",
    )
    return PrinterTestResult(ok=result.ok, message=result.message)


@router.delete("/{printer_id}", status_code=204)
def delete_printer(printer_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    printer = db.get(Printer, printer_id)
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    db.delete(printer)
    db.commit()
