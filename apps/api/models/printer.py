import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.base import Base
from apps.api.models.enums import PrinterProtocol, PrinterStatus


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Printer(Base):
    """A network printer the server prints to directly - IPP or raw AppSocket.

    No agent process is involved: SecurePrint's own backend opens the
    connection to the printer's IP/hostname and streams the sanitized PDF, the
    same way a CUPS server or any managed print service does.
    """

    __tablename__ = "printers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), default="")

    protocol: Mapped[PrinterProtocol] = mapped_column(Enum(PrinterProtocol), default=PrinterProtocol.IPP)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=631)
    ipp_path: Mapped[str] = mapped_column(String(255), default="/ipp/print")
    use_tls: Mapped[bool] = mapped_column(default=False)

    status: Mapped[PrinterStatus] = mapped_column(Enum(PrinterStatus), default=PrinterStatus.UNKNOWN)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_message: Mapped[str] = mapped_column(String(500), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    print_jobs = relationship("PrintJob", back_populates="printer")
