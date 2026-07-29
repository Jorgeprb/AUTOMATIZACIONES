"""Extract text for clinic knowledge imports from PDFs and web pages."""

from __future__ import annotations

import io
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_URL_BYTES = 1 * 1024 * 1024
MAX_KNOWLEDGE_CHARS = 30_000


class KnowledgeImportError(ValueError):
    """Stable user-facing import error."""


@dataclass(frozen=True, slots=True)
class ExtractedKnowledge:
    """Clean extracted text and metadata before persistence."""

    title: str
    content: str
    source: str


class _HTMLTextExtractor(HTMLParser):
    """Small stdlib HTML cleaner for public pages."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._title_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if lowered == "title":
            self._title_depth += 1
        if lowered in {"p", "br", "li", "h1", "h2", "h3", "section", "article"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if lowered == "title" and self._title_depth:
            self._title_depth -= 1
        if lowered in {"p", "li", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        if self._title_depth:
            self.title_parts.append(data)
        if self._skip_depth:
            return
        self.text_parts.append(data)


def normalize_extracted_text(value: str) -> str:
    """Collapse noisy extracted text without losing paragraph breaks."""
    text = re.sub(r"\r\n?", "\n", value)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _limit_text(value: str) -> str:
    """Keep prompt context bounded."""
    if len(value) <= MAX_KNOWLEDGE_CHARS:
        return value
    return value[:MAX_KNOWLEDGE_CHARS].rstrip()


def extract_pdf_knowledge(data: bytes, *, filename: str) -> ExtractedKnowledge:
    """Extract readable text from one uploaded PDF."""
    if not data:
        raise KnowledgeImportError("El PDF está vacío.")
    if len(data) > MAX_PDF_BYTES:
        raise KnowledgeImportError("El PDF supera el tamaño máximo de 5 MB.")
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency exists in deploys
        raise KnowledgeImportError(
            "Falta la dependencia pypdf para extraer texto de PDF."
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = [page.extract_text() or "" for page in reader.pages[:50]]
    except Exception as exc:  # pypdf can raise several parsing exceptions
        raise KnowledgeImportError("No se pudo leer el PDF.") from exc
    content = _limit_text(normalize_extracted_text("\n\n".join(parts)))
    if not content:
        raise KnowledgeImportError("No se encontró texto legible en el PDF.")
    clean_filename = filename.strip() or "documento.pdf"
    return ExtractedKnowledge(
        title=clean_filename.rsplit(".", maxsplit=1)[0][:240],
        content=content,
        source=clean_filename[:1000],
    )


def _read_limited_response(response: httpx.Response) -> bytes:
    """Read a streamed response with a hard byte cap."""
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_URL_BYTES:
            raise KnowledgeImportError("La URL supera el tamaño máximo de 1 MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_response(data: bytes, headers: httpx.Headers) -> str:
    """Decode response bytes using declared or default UTF-8 encoding."""
    content_type = headers.get("content-type", "")
    match = re.search(r"charset=([\w.-]+)", content_type, flags=re.IGNORECASE)
    encoding = match.group(1) if match else "utf-8"
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def _validate_public_url(url: str) -> None:
    """Reject URLs that can reach loopback, private, metadata, or local networks."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise KnowledgeImportError("La URL debe empezar por http:// o https://.")
    if parsed.username or parsed.password:
        raise KnowledgeImportError("La URL no puede contener credenciales.")
    if parsed.port not in {None, 80, 443}:
        raise KnowledgeImportError("La URL utiliza un puerto no permitido.")
    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(
        ".local"
    ):
        raise KnowledgeImportError("La URL apunta a una red no permitida.")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise KnowledgeImportError("No se pudo resolver el dominio de la URL.") from exc
    if not addresses:
        raise KnowledgeImportError("El dominio no tiene direcciones utilizables.")
    for raw_address in addresses:
        address = ipaddress.ip_address(str(raw_address).split("%", 1)[0])
        if not address.is_global:
            raise KnowledgeImportError("La URL apunta a una red privada o reservada.")


def fetch_url_knowledge(url: str) -> ExtractedKnowledge:
    """Download one bounded public page while preventing SSRF and redirect bypasses."""
    current_url = url.strip()
    _validate_public_url(current_url)
    headers: httpx.Headers | None = None
    data = b""
    final_url = current_url
    with httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(12.0, connect=5.0),
        trust_env=False,
        headers={"User-Agent": "AutogalKnowledgeImporter/1.0"},
    ) as client:
        for redirect_count in range(4):
            _validate_public_url(current_url)
            try:
                with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count >= 3:
                            raise KnowledgeImportError(
                                "La URL tiene demasiadas redirecciones."
                            )
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").casefold()
                    if content_type and not any(
                        allowed in content_type
                        for allowed in ("text/", "application/xhtml+xml")
                    ):
                        raise KnowledgeImportError(
                            "La URL no devuelve contenido de texto compatible."
                        )
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > MAX_URL_BYTES:
                        raise KnowledgeImportError(
                            "La URL supera el tamaño máximo de 1 MB."
                        )
                    data = _read_limited_response(response)
                    headers = response.headers
                    final_url = str(response.url)
                    break
            except KnowledgeImportError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                raise KnowledgeImportError("No se pudo descargar la URL.") from exc
        else:  # pragma: no cover - defensive loop guard
            raise KnowledgeImportError("La URL tiene demasiadas redirecciones.")

    if headers is None:
        raise KnowledgeImportError("No se pudo descargar la URL.")
    raw = _decode_response(data, headers)
    content_type = headers.get("content-type", "").casefold()
    final_parsed = urlparse(final_url)
    if "html" in content_type or "<html" in raw[:500].casefold():
        parser = _HTMLTextExtractor()
        parser.feed(raw)
        title = normalize_extracted_text(" ".join(parser.title_parts))
        content = normalize_extracted_text(" ".join(parser.text_parts))
    else:
        title = final_parsed.netloc
        content = normalize_extracted_text(raw)
    content = _limit_text(content)
    if not content:
        raise KnowledgeImportError("No se encontró texto legible en la URL.")
    return ExtractedKnowledge(
        title=(title or final_parsed.netloc)[:240],
        content=content,
        source=final_url[:1000],
    )
