from datetime import datetime

from pydantic import BaseModel


class PrinterOut(BaseModel):
    id: str
    name: str
    location: str
    protocol: str
    host: str
    port: int
    ipp_path: str
    use_tls: bool
    status: str
    last_tested_at: datetime | None
    last_test_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PrinterCreate(BaseModel):
    name: str
    location: str = ""
    protocol: str = "IPP"
    host: str
    port: int = 631
    ipp_path: str = "/ipp/print"
    use_tls: bool = False


class PrinterTestResult(BaseModel):
    ok: bool
    message: str
