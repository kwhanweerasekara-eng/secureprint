"""Direct network printing - the SecurePrint backend talks to real printers
itself over IPP or raw AppSocket (port 9100 "JetDirect" streaming), the same
way a CUPS server or any managed print service does. No separate agent
process is involved: registering a printer and printing to it both happen
entirely through the web API.

IPP (RFC 8010/8011) is implemented here directly rather than pulling in a
client library, since only two operations are needed (Get-Printer-Attributes
for connectivity testing, Print-Job for delivery) and a minimal encoder/
decoder keeps the wire format fully inspectable.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

import requests

CHARSET = "utf-8"
LANGUAGE = "en"
REQUESTING_USER = "secureprint"

# IPP delimiter tags
OPERATION_ATTRIBUTES_TAG = 0x01
JOB_ATTRIBUTES_TAG = 0x02
END_OF_ATTRIBUTES_TAG = 0x03

# IPP value tags used here
TAG_INTEGER = 0x21
TAG_ENUM = 0x23
TAG_KEYWORD = 0x44
TAG_URI = 0x45
TAG_CHARSET = 0x47
TAG_NATURAL_LANGUAGE = 0x48
TAG_MIME_MEDIA_TYPE = 0x49
TAG_NAME_WITHOUT_LANGUAGE = 0x42

# IPP operation ids
OP_PRINT_JOB = 0x0002
OP_GET_PRINTER_ATTRIBUTES = 0x000B

PRINTER_STATE_LABELS = {3: "idle", 4: "processing", 5: "stopped"}

SIDES = ("one-sided", "two-sided-long-edge", "two-sided-short-edge")


class PrintDeliveryError(Exception):
    """Raised when a printer could not be reached or rejected the job."""


@dataclass
class ConnectionResult:
    ok: bool
    message: str


@dataclass
class PrintOptions:
    """Settings the user chose in the Print dialog, passed on to the printer."""
    copies: int = 1
    sides: str | None = None  # None leaves the printer's own default

    def describe(self) -> str:
        parts = [f"{self.copies} copies"] if self.copies > 1 else []
        if self.sides and self.sides != "one-sided":
            parts.append("two-sided")
        return f" ({', '.join(parts)})" if parts else ""


def _printer_uri(host: str, port: int, ipp_path: str, use_tls: bool) -> str:
    scheme = "ipps" if use_tls else "ipp"
    path = ipp_path if ipp_path.startswith("/") else f"/{ipp_path}"
    return f"{scheme}://{host}:{port}{path}"


def _http_url(host: str, port: int, ipp_path: str, use_tls: bool) -> str:
    scheme = "https" if use_tls else "http"
    path = ipp_path if ipp_path.startswith("/") else f"/{ipp_path}"
    return f"{scheme}://{host}:{port}{path}"


def _pack_attr(tag: int, name: str, value: bytes) -> bytes:
    name_b = name.encode("ascii")
    return bytes([tag]) + len(name_b).to_bytes(2, "big") + name_b + len(value).to_bytes(2, "big") + value


def _pack_additional_value(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + (0).to_bytes(2, "big") + len(value).to_bytes(2, "big") + value


def _build_request(operation_id: int, printer_uri: str, extra_attrs: bytes = b"") -> bytes:
    body = bytes([1, 1])  # IPP/1.1
    body += operation_id.to_bytes(2, "big")
    body += (1).to_bytes(4, "big")  # request-id
    body += bytes([OPERATION_ATTRIBUTES_TAG])
    body += _pack_attr(TAG_CHARSET, "attributes-charset", CHARSET.encode("ascii"))
    body += _pack_attr(TAG_NATURAL_LANGUAGE, "attributes-natural-language", LANGUAGE.encode("ascii"))
    body += _pack_attr(TAG_URI, "printer-uri", printer_uri.encode("ascii"))
    body += _pack_attr(TAG_NAME_WITHOUT_LANGUAGE, "requesting-user-name", REQUESTING_USER.encode("utf-8"))
    body += extra_attrs
    body += bytes([END_OF_ATTRIBUTES_TAG])
    return body


def _build_get_printer_attributes(printer_uri: str) -> bytes:
    requested = _pack_attr(TAG_KEYWORD, "requested-attributes", b"printer-state")
    requested += _pack_additional_value(TAG_KEYWORD, b"printer-state-reasons")
    requested += _pack_additional_value(TAG_KEYWORD, b"printer-name")
    return _build_request(OP_GET_PRINTER_ATTRIBUTES, printer_uri, requested)


def _build_print_job(printer_uri: str, job_name: str, document_format: str = "application/pdf",
                     options: PrintOptions | None = None) -> bytes:
    extra = _pack_attr(TAG_NAME_WITHOUT_LANGUAGE, "job-name", job_name.encode("utf-8"))
    extra += _pack_attr(TAG_MIME_MEDIA_TYPE, "document-format", document_format.encode("ascii"))
    if options and (options.copies > 1 or options.sides):
        extra += bytes([JOB_ATTRIBUTES_TAG])
        if options.copies > 1:
            extra += _pack_attr(TAG_INTEGER, "copies", options.copies.to_bytes(4, "big"))
        if options.sides:
            extra += _pack_attr(TAG_KEYWORD, "sides", options.sides.encode("ascii"))
    return _build_request(OP_PRINT_JOB, printer_uri, extra)


def _parse_response(data: bytes) -> dict:
    status_code = int.from_bytes(data[2:4], "big")
    pos = 8
    attributes: dict[str, list[bytes]] = {}
    last_key: str | None = None
    while pos < len(data):
        tag = data[pos]
        pos += 1
        if tag <= 0x0F:  # delimiter tag (operation/job/printer/unsupported/end groups)
            if tag == END_OF_ATTRIBUTES_TAG:
                break
            last_key = None
            continue
        if pos + 2 > len(data):
            break
        name_len = int.from_bytes(data[pos : pos + 2], "big")
        pos += 2
        name = data[pos : pos + name_len].decode("utf-8", "replace")
        pos += name_len
        value_len = int.from_bytes(data[pos : pos + 2], "big")
        pos += 2
        value = data[pos : pos + value_len]
        pos += value_len
        if name:
            attributes[name] = [value]
            last_key = name
        elif last_key:
            attributes[last_key].append(value)
    return {"status_code": status_code, "attributes": attributes}


def _describe_printer_state(attributes: dict[str, list[bytes]]) -> str:
    state_values = attributes.get("printer-state")
    if not state_values:
        return "printer responded"
    state_int = int.from_bytes(state_values[0], "big") if len(state_values[0]) == 4 else None
    label = PRINTER_STATE_LABELS.get(state_int, f"state {state_int}")
    reasons = attributes.get("printer-state-reasons")
    if reasons:
        reason_text = ", ".join(r.decode("utf-8", "replace") for r in reasons if r != b"none")
        if reason_text:
            return f"{label} ({reason_text})"
    return label


def test_ipp_printer(host: str, port: int, ipp_path: str, use_tls: bool, timeout: float = 5) -> ConnectionResult:
    uri = _printer_uri(host, port, ipp_path, use_tls)
    url = _http_url(host, port, ipp_path, use_tls)
    try:
        resp = requests.post(
            url, data=_build_get_printer_attributes(uri), headers={"Content-Type": "application/ipp"}, timeout=timeout, verify=False
        )
    except requests.RequestException as exc:
        return ConnectionResult(False, f"Connection failed: {exc}")

    if resp.status_code != 200:
        return ConnectionResult(False, f"Printer returned HTTP {resp.status_code}")

    parsed = _parse_response(resp.content)
    if parsed["status_code"] >= 0x0100:
        return ConnectionResult(False, f"IPP error status 0x{parsed['status_code']:04x}")

    return ConnectionResult(True, f"IPP printer responded - {_describe_printer_state(parsed['attributes'])}")


def print_via_ipp(host: str, port: int, ipp_path: str, use_tls: bool, pdf_bytes: bytes, job_name: str, timeout: float = 60,
                  options: PrintOptions | None = None) -> None:
    uri = _printer_uri(host, port, ipp_path, use_tls)
    url = _http_url(host, port, ipp_path, use_tls)
    request_body = _build_print_job(uri, job_name, options=options) + pdf_bytes
    try:
        resp = requests.post(url, data=request_body, headers={"Content-Type": "application/ipp"}, timeout=timeout, verify=False)
    except requests.RequestException as exc:
        raise PrintDeliveryError(f"Connection failed: {exc}") from exc

    if resp.status_code != 200:
        raise PrintDeliveryError(f"Printer returned HTTP {resp.status_code}")

    parsed = _parse_response(resp.content)
    if parsed["status_code"] >= 0x0100:
        raise PrintDeliveryError(f"IPP error status 0x{parsed['status_code']:04x}")


def test_socket_printer(host: str, port: int, timeout: float = 5) -> ConnectionResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        return ConnectionResult(False, f"Connection failed: {exc}")
    return ConnectionResult(True, f"TCP connection to {host}:{port} succeeded")


def print_via_socket(host: str, port: int, pdf_bytes: bytes, timeout: float = 60, copies: int = 1) -> None:
    # A raw socket printer has no job settings, so each copy is sent as its own
    # stream. Two-sided printing is left to the printer's default.
    try:
        for _ in range(copies):
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.sendall(pdf_bytes)
    except OSError as exc:
        raise PrintDeliveryError(f"Socket print failed: {exc}") from exc


def test_printer(protocol: str, host: str, port: int, ipp_path: str, use_tls: bool) -> ConnectionResult:
    if protocol == "SOCKET":
        return test_socket_printer(host, port)
    return test_ipp_printer(host, port, ipp_path, use_tls)


def print_to_printer(protocol: str, host: str, port: int, ipp_path: str, use_tls: bool, pdf_bytes: bytes, job_name: str,
                     options: PrintOptions | None = None) -> None:
    options = options or PrintOptions()
    if protocol == "SOCKET":
        print_via_socket(host, port, pdf_bytes, copies=options.copies)
    else:
        print_via_ipp(host, port, ipp_path, use_tls, pdf_bytes, job_name, options=options)
