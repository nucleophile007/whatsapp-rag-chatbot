import os
import json
import logging
import re
import socket
from collections import deque
from html.parser import HTMLParser
from ipaddress import ip_address
from typing import Any, List, Optional, Set
from urllib.parse import urljoin, urlparse, urlunparse
from functools import lru_cache
import xml.etree.ElementTree as ET
import requests
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
EMBEDDING_MODEL_NAME = "models/gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "3072"))
WEB_CRAWLER_MAX_PAGES_PER_SITE = max(1, int(os.getenv("WEB_CRAWLER_MAX_PAGES_PER_SITE", "50")))
WEB_CRAWLER_TIMEOUT_SECONDS = max(3, int(os.getenv("WEB_CRAWLER_TIMEOUT_SECONDS", "12")))
WEB_CRAWLER_USER_AGENT = os.getenv("WEB_CRAWLER_USER_AGENT", "async-rag-bot/1.0")
WEB_CRAWLER_USE_SITEMAP = os.getenv("WEB_CRAWLER_USE_SITEMAP", "true").strip().lower() in {"1", "true", "yes", "on"}
WEB_CRAWLER_MAX_SITEMAP_URLS = max(0, int(os.getenv("WEB_CRAWLER_MAX_SITEMAP_URLS", "500")))
DEFAULT_CHUNK_SIZE = max(200, int(os.getenv("RAG_CHUNK_SIZE", "1000")))
DEFAULT_CHUNK_OVERLAP = max(0, int(os.getenv("RAG_CHUNK_OVERLAP", "200")))

_NON_HTML_EXTENSIONS = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".mp4",
    ".mp3",
    ".avi",
    ".mov",
    ".css",
    ".js",
    ".xml",
)


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML parser to extract readable text and links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._text_parts: List[str] = []
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if lowered == "a":
            href = next((value for key, value in attrs if key == "href"), None)
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        clean = " ".join(data.split())
        if clean:
            self._text_parts.append(clean)

    def get_text(self) -> str:
        return " ".join(self._text_parts).strip()


_SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_NEXT_PUSH_PAYLOAD_RE = re.compile(
    r"self\.__next_f\.push\(\[\d+,\s*\"((?:[^\"\\]|\\.)*)\"\]\)",
    re.DOTALL,
)
_SCRIPT_URL_LITERAL_RE = re.compile(
    r"""["'](https?://[^"'\s<>]+|/[A-Za-z0-9][A-Za-z0-9/_\-]{0,220})["']""",
    re.IGNORECASE,
)
_JSON_LD_KEY_RE = re.compile(r'type\s*=\s*["\']application/ld\+json["\']', re.IGNORECASE)
_JSON_TYPE_KEY_RE = re.compile(r'type\s*=\s*["\']application/(?:ld\+)?json["\']', re.IGNORECASE)
_MAX_SCRIPT_JSON_CANDIDATES = 150
_MAX_JSON_FRAGMENT_BYTES = 350_000


def _decode_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return value


def _normalize_text_fragment(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _is_meaningful_text(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if lowered.startswith(("http://", "https://", "/_next/", "static/chunks/")):
        return False
    if len(value) > 1200:
        return False
    if len(value) < 2:
        return False
    if re.fullmatch(r"[A-Za-z0-9_\-./:@]+", value) and len(value) > 80:
        return False
    return any(ch.isalpha() for ch in value)


def _extract_balanced_fragment(text: str, start_index: int) -> str:
    if start_index < 0 or start_index >= len(text):
        return ""
    opening = text[start_index]
    if opening not in "{[":
        return ""
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escape = False

    for i in range(start_index, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == opening:
            depth += 1
            continue
        if ch == closing:
            depth -= 1
            if depth == 0:
                return text[start_index : i + 1]
    return ""


def _collect_text_from_json(value: Any, output: List[str]) -> None:
    if isinstance(value, dict):
        for _, nested in value.items():
            _collect_text_from_json(nested, output)
        return
    if isinstance(value, list):
        for nested in value:
            _collect_text_from_json(nested, output)
        return
    if isinstance(value, str):
        normalized = _normalize_text_fragment(value)
        if _is_meaningful_text(normalized):
            output.append(normalized)


def _extract_json_fragments_from_text(text: str) -> List[str]:
    fragments: List[str] = []
    idx = 0
    attempts = 0

    while idx < len(text) and attempts < _MAX_SCRIPT_JSON_CANDIDATES:
        next_obj = text.find("{", idx)
        next_arr = text.find("[", idx)

        if next_obj == -1 and next_arr == -1:
            break
        if next_obj == -1:
            start = next_arr
        elif next_arr == -1:
            start = next_obj
        else:
            start = min(next_obj, next_arr)

        attempts += 1
        fragment = _extract_balanced_fragment(text, start)
        idx = start + 1
        if not fragment:
            continue
        if len(fragment) < 8 or len(fragment) > _MAX_JSON_FRAGMENT_BYTES:
            continue

        if fragment[0] == "{" and ('":' not in fragment and "':" not in fragment):
            continue
        if fragment[0] == "[" and ('"' not in fragment and "{" not in fragment):
            continue

        fragments.append(fragment)
        idx = max(idx, start + len(fragment))

    return fragments


def _extract_useful_text_from_payload(payload: str) -> List[str]:
    extracted: List[str] = []

    stripped = (payload or "").strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed_root = json.loads(stripped)
            _collect_text_from_json(parsed_root, extracted)
        except Exception:
            pass

    for fragment in _extract_json_fragments_from_text(stripped):
        try:
            parsed = json.loads(fragment)
        except Exception:
            continue
        _collect_text_from_json(parsed, extracted)

    deduped: List[str] = []
    seen = set()
    for piece in extracted:
        if piece in seen:
            continue
        seen.add(piece)
        deduped.append(piece)
    return deduped


def _extract_structured_script_text(html_payload: str) -> str:
    structured_parts: List[str] = []

    for attrs_raw, body in _SCRIPT_TAG_RE.findall(html_payload or ""):
        attrs_lower = (attrs_raw or "").lower()
        script_body = (body or "").strip()
        if not script_body:
            continue

        # JSON-LD script blocks.
        if _JSON_LD_KEY_RE.search(attrs_lower):
            try:
                parsed = json.loads(script_body)
                _collect_text_from_json(parsed, structured_parts)
            except Exception:
                pass
        elif _JSON_TYPE_KEY_RE.search(attrs_lower):
            structured_parts.extend(_extract_useful_text_from_payload(script_body))

        # Next.js app-router hydration payload (self.__next_f.push).
        if "self.__next_f.push" in script_body:
            for encoded_payload in _NEXT_PUSH_PAYLOAD_RE.findall(script_body):
                decoded_payload = _decode_json_string(encoded_payload)
                structured_parts.extend(_extract_useful_text_from_payload(decoded_payload))
        elif "{" in script_body or "[" in script_body:
            # Generic fallback for other frameworks embedding JSON in script tags.
            structured_parts.extend(_extract_useful_text_from_payload(script_body))

    deduped: List[str] = []
    seen = set()
    for piece in structured_parts:
        normalized = _normalize_text_fragment(piece)
        if not _is_meaningful_text(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return "\n".join(deduped)


def _normalize_url(raw_url: str) -> str:
    candidate = (raw_url or "").strip()
    if not candidate:
        raise ValueError("Empty URL is not allowed.")
    parsed = urlparse(candidate)
    if not parsed.scheme:
        parsed = urlparse(f"https://{candidate}")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme for '{raw_url}'. Use http/https.")

    path = parsed.path or "/"
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        fragment="",
    )
    return urlunparse(normalized)


def _is_safe_public_host(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname in {"localhost", "0.0.0.0", "::1"} or hostname.endswith(".local"):
        return False
    try:
        resolved = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    for result in resolved:
        ip_raw = result[4][0]
        ip = ip_address(ip_raw)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def _is_crawlable_child_url(candidate_url: str, allowed_hosts: Set[str]) -> bool:
    child = urlparse(candidate_url)

    if child.scheme not in {"http", "https"}:
        return False
    if (child.netloc or "").lower() not in allowed_hosts:
        return False
    path = (child.path or "").lower()
    if any(path.endswith(ext) for ext in _NON_HTML_EXTENSIONS):
        return False
    return True


def _www_ssl_fallback_url(url: str, err: Exception) -> Optional[str]:
    """Retry with www host for sites whose cert is valid only for www.<domain>."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    if not host or host.startswith("www."):
        return None
    if parsed.scheme != "https":
        return None

    msg = str(err).lower()
    ssl_indicators = (
        "certificateerror",
        "hostname",
        "err_cert",
        "ssl: certificate_verify_failed",
        "common_name_invalid",
    )
    if not any(indicator in msg for indicator in ssl_indicators):
        return None

    fallback_host = f"www.{host}"
    fallback_url = urlunparse(
        parsed._replace(
            netloc=fallback_host,
            fragment="",
        )
    )
    return fallback_url


def _discover_sitemap_urls(seed_url: str) -> List[str]:
    if WEB_CRAWLER_MAX_SITEMAP_URLS <= 0:
        return []

    parsed = urlparse(seed_url)
    root_host = (parsed.netloc or "").lower()
    sitemap_candidates = [
        urlunparse(parsed._replace(path="/sitemap.xml", params="", query="", fragment="")),
        urlunparse(parsed._replace(path="/sitemap_index.xml", params="", query="", fragment="")),
        urlunparse(parsed._replace(path="/sitemap-index.xml", params="", query="", fragment="")),
    ]

    robots_url = urlunparse(parsed._replace(path="/robots.txt", params="", query="", fragment=""))
    try:
        robots_response = requests.get(
            robots_url,
            timeout=WEB_CRAWLER_TIMEOUT_SECONDS,
            headers={"User-Agent": WEB_CRAWLER_USER_AGENT},
            allow_redirects=True,
        )
        if robots_response.ok:
            for line in (robots_response.text or "").splitlines():
                stripped = line.strip()
                if not stripped.lower().startswith("sitemap:"):
                    continue
                sitemap_value = stripped.split(":", 1)[1].strip()
                if not sitemap_value:
                    continue
                try:
                    normalized_sitemap = _normalize_url(sitemap_value)
                except ValueError:
                    continue
                if (urlparse(normalized_sitemap).netloc or "").lower() == root_host:
                    sitemap_candidates.append(normalized_sitemap)
    except Exception:
        pass

    discovered: List[str] = []
    seen_sitemaps: Set[str] = set()
    pending_sitemaps = deque(sitemap_candidates)

    while pending_sitemaps and len(discovered) < WEB_CRAWLER_MAX_SITEMAP_URLS:
        current_sitemap = pending_sitemaps.popleft()
        if current_sitemap in seen_sitemaps:
            continue
        seen_sitemaps.add(current_sitemap)

        try:
            response = requests.get(
                current_sitemap,
                timeout=WEB_CRAWLER_TIMEOUT_SECONDS,
                headers={"User-Agent": WEB_CRAWLER_USER_AGENT},
                allow_redirects=True,
            )
            response.raise_for_status()
            xml_payload = response.text or ""
            if not xml_payload.strip():
                continue
            root = ET.fromstring(xml_payload)
        except Exception:
            continue

        loc_elements = root.findall(".//{*}loc")
        for loc in loc_elements:
            raw_loc = (loc.text or "").strip()
            if not raw_loc:
                continue
            try:
                normalized = _normalize_url(raw_loc)
            except ValueError:
                continue
            loc_parsed = urlparse(normalized)
            loc_host = (loc_parsed.netloc or "").lower()
            if loc_host != root_host:
                continue
            path = (loc_parsed.path or "").lower()
            if path.endswith(".xml"):
                if normalized not in seen_sitemaps:
                    pending_sitemaps.append(normalized)
                continue
            if normalized not in discovered:
                discovered.append(normalized)
            if len(discovered) >= WEB_CRAWLER_MAX_SITEMAP_URLS:
                break

    return discovered


def _build_seed_queue(normalized_seed: str, use_sitemap: bool) -> deque:
    seed_queue = deque([normalized_seed])
    if use_sitemap:
        for sitemap_url in _discover_sitemap_urls(normalized_seed):
            if sitemap_url not in seed_queue:
                seed_queue.append(sitemap_url)
    return seed_queue


def _extract_text_and_links_from_html(html_payload: str, base_url: str) -> tuple[str, List[str]]:
    parser = _HTMLTextExtractor()
    parser.feed(html_payload or "")
    parser.close()

    extracted_links: List[str] = []
    for href in parser.links:
        lowered_href = href.strip().lower()
        if not lowered_href or lowered_href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        try:
            normalized_next = _normalize_url(urljoin(base_url, href))
            extracted_links.append(normalized_next)
        except ValueError:
            continue

    # Frameworks (SSR/SSG) often include route URLs inside script payloads.
    # Extract URL literals generically to improve internal page discovery.
    for match in _SCRIPT_URL_LITERAL_RE.finditer(html_payload or ""):
        literal_url = (match.group(1) or "").strip()
        if not literal_url:
            continue
        if literal_url.startswith("/_next/"):
            continue
        try:
            normalized_next = _normalize_url(urljoin(base_url, literal_url))
            extracted_links.append(normalized_next)
        except ValueError:
            continue

    deduped_links: List[str] = []
    seen_links = set()
    for link in extracted_links:
        if link in seen_links:
            continue
        seen_links.add(link)
        deduped_links.append(link)

    visible_text = parser.get_text()
    structured_text = _extract_structured_script_text(html_payload or "")

    if structured_text:
        if visible_text:
            merged_text = f"{visible_text}\n{structured_text}"
        else:
            merged_text = structured_text
    else:
        merged_text = visible_text

    return merged_text, deduped_links


def _extract_documents_from_site(seed_url: str, max_pages: int, use_sitemap: bool) -> List[Document]:
    normalized_seed = _normalize_url(seed_url)
    if not _is_safe_public_host(normalized_seed):
        raise ValueError(f"Unsafe or non-public URL blocked: {seed_url}")

    allowed_hosts: Set[str] = {(urlparse(normalized_seed).netloc or "").lower()}
    to_visit = _build_seed_queue(normalized_seed, use_sitemap)
    visited = set()
    documents: List[Document] = []

    while to_visit and len(visited) < max_pages:
        current = to_visit.popleft()
        if current in visited:
            continue
        visited.add(current)

        try:
            response = requests.get(
                current,
                timeout=WEB_CRAWLER_TIMEOUT_SECONDS,
                headers={"User-Agent": WEB_CRAWLER_USER_AGENT},
                allow_redirects=True,
            )
            if response.status_code in {401, 403, 429}:
                if current == normalized_seed:
                    raise ValueError(
                        f"Website blocked crawler access for '{seed_url}' (HTTP {response.status_code}). "
                        "Whitelist this server IP/user-agent or provide publicly accessible pages."
                    )
                logger.warning(f"Website crawl blocked for {current}: HTTP {response.status_code}")
                continue
            response.raise_for_status()
        except requests.exceptions.SSLError as e:
            fallback_url = _www_ssl_fallback_url(current, e)
            if fallback_url and fallback_url not in visited and _is_safe_public_host(fallback_url):
                logger.info(f"Retrying SSL hostname mismatch with fallback URL: {fallback_url}")
                to_visit.appendleft(fallback_url)
                continue
            logger.warning(f"Website crawl failed for {current}: {e}")
            continue
        except requests.exceptions.HTTPError as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if current == normalized_seed:
                if status_code is not None:
                    raise ValueError(f"Failed to crawl '{seed_url}' (HTTP {status_code}).")
                raise ValueError(f"Failed to crawl '{seed_url}' due to HTTP error.")
            logger.warning(f"Website crawl failed for {current}: {e}")
            continue
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Website crawl failed for {current}: {e}")
            continue

        base_url = response.url or current
        base_host = (urlparse(base_url).netloc or "").lower()
        if base_host:
            allowed_hosts.add(base_host)

        content_type = (response.headers.get("content-type") or "").lower()
        if content_type and ("text/html" not in content_type and "application/xhtml+xml" not in content_type):
            continue

        page_text, extracted_links = _extract_text_and_links_from_html(response.text or "", base_url)
        if page_text:
            documents.append(
                Document(
                    page_content=page_text,
                    metadata={
                        "source": base_url,
                        "source_type": "website",
                    },
                )
            )

        for next_url in extracted_links:
            if next_url in visited:
                continue
            if not _is_crawlable_child_url(next_url, allowed_hosts):
                continue
            to_visit.append(next_url)

    return documents


def _index_documents_to_collection(
    collection_name: str,
    documents: List[Document],
    force_recreate: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> int:
    if not GOOGLE_API_KEY:
        raise ValueError("Bhai, GOOGLE_API_KEY toh daal do!")

    embedding_model = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL_NAME)
    expected_dimension = get_embedding_dimension()
    ensure_qdrant_collection(
        collection_name=collection_name,
        vector_size=expected_dimension,
        force_recreate=force_recreate,
    )

    if not documents:
        return 0

    safe_chunk_size = max(200, int(chunk_size))
    safe_chunk_overlap = max(0, min(int(chunk_overlap), safe_chunk_size - 1))
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=safe_chunk_size,
        chunk_overlap=safe_chunk_overlap,
    )
    all_chunks = text_splitter.split_documents(documents)

    if not all_chunks:
        return 0

    logger.info(f"Uploading {len(all_chunks)} chunks to: {collection_name}")
    QdrantVectorStore.from_documents(
        documents=all_chunks,
        embedding=embedding_model,
        url=QDRANT_URL,
        collection_name=collection_name,
    )
    return len(all_chunks)

@lru_cache(maxsize=1)
def get_embedding_dimension() -> int:
    """
    Embedding dimension resolve karo.
    Priority:
    1) EMBEDDING_DIMENSION env
    2) Probe the configured embedding model
    3) Fallback default (3072)
    """
    configured_dimension = os.getenv("EMBEDDING_DIMENSION")
    if configured_dimension:
        return int(configured_dimension)

    if not GOOGLE_API_KEY:
        return DEFAULT_EMBEDDING_DIMENSION

    try:
        embedding_model = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL_NAME)
        probe_vector = embedding_model.embed_query("dimension probe")
        return len(probe_vector)
    except Exception as e:
        logger.warning(f"Embedding dimension probe failed, fallback to {DEFAULT_EMBEDDING_DIMENSION}: {e}")
        return DEFAULT_EMBEDDING_DIMENSION


def _extract_collection_vector_size(collection_info) -> int:
    vectors = collection_info.config.params.vectors

    # Named vectors case
    if isinstance(vectors, dict):
        first_vector_config = next(iter(vectors.values()), None)
        return getattr(first_vector_config, "size", None)

    # Single dense vector case
    return getattr(vectors, "size", None)


def ensure_qdrant_collection(
    collection_name: str,
    vector_size: int,
    force_recreate: bool = False,
):
    """Collection ko expected vector size ke saath ensure karo."""
    client = QdrantClient(url=QDRANT_URL)

    # Dekh lete hain pehle se toh nahi hai
    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)

    if not exists:
        logger.info(f"Nayi Qdrant collection ban rahi hai: {collection_name} (dim={vector_size})")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
        return "created"

    if force_recreate:
        logger.warning(f"Force recreate enabled. Recreating collection '{collection_name}'.")
        client.delete_collection(collection_name=collection_name)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
        return "recreated"

    collection_info = client.get_collection(collection_name)
    existing_size = _extract_collection_vector_size(collection_info)

    if existing_size is not None and existing_size != vector_size:
        if not force_recreate:
            raise ValueError(
                f"Existing Qdrant collection is configured for dense vectors with {existing_size} dimensions. "
                f"Selected embeddings are {vector_size}-dimensional. "
                "If you want to recreate the collection, set `force_recreate` parameter to `True`."
            )

        logger.warning(
            f"Recreating collection '{collection_name}' due to dimension mismatch: "
            f"{existing_size} -> {vector_size}"
        )
        client.delete_collection(collection_name=collection_name)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
        return "recreated"

    return "reused"


def create_qdrant_collection(collection_name: str, force_recreate: bool = False):
    """Qdrant mein collection banate/validate karte hain expected embedding dimension ke saath."""
    return ensure_qdrant_collection(
        collection_name=collection_name,
        vector_size=get_embedding_dimension(),
        force_recreate=force_recreate,
    )


def index_pdfs_to_collection(
    collection_name: str,
    file_paths: List[str],
    force_recreate: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
):
    """PDFs ko read karke aur tukde-tukde karke Qdrant mein daalte hain (Gyan Ka Sagar)"""
    documents: List[Document] = []
    for file_path in file_paths:
        logger.info(f"File index ho rahi hai: {file_path}")
        loader = PyPDFLoader(file_path=file_path)
        docs = loader.load()
        for doc in docs:
            doc.metadata = {**doc.metadata, "source_type": "pdf"}
        documents.extend(docs)

    if not documents:
        logger.warning("PDF mein kuch kaam ka nahi mila bhai.")
        return 0

    return _index_documents_to_collection(
        collection_name=collection_name,
        documents=documents,
        force_recreate=force_recreate,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def index_urls_to_collection(
    collection_name: str,
    urls: List[str],
    force_recreate: bool = False,
    max_pages_per_site: Optional[int] = None,
    use_sitemap: Optional[bool] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> int:
    """Website URLs crawl karke unka text Qdrant collection mein index karo (static HTML crawler)."""
    crawl_limit = max_pages_per_site or WEB_CRAWLER_MAX_PAGES_PER_SITE
    crawl_limit = max(1, crawl_limit)
    sitemap_mode = WEB_CRAWLER_USE_SITEMAP if use_sitemap is None else bool(use_sitemap)

    documents: List[Document] = []
    failures: List[str] = []
    for url in urls:
        clean_url = (url or "").strip()
        if not clean_url:
            continue
        logger.info(f"Website crawl start (static): {clean_url}")
        try:
            site_docs = _extract_documents_from_site(
                clean_url,
                max_pages=crawl_limit,
                use_sitemap=sitemap_mode,
            )
        except ValueError as e:
            failure = str(e)
            failures.append(failure)
            logger.warning(f"Website crawl validation failed for {clean_url}: {failure}")
            continue
        documents.extend(site_docs)

    if not documents:
        if failures:
            raise ValueError(" ; ".join(failures))
        logger.warning("Website se koi crawlable content nahi mila.")
        return 0

    return _index_documents_to_collection(
        collection_name=collection_name,
        documents=documents,
        force_recreate=force_recreate,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

def list_qdrant_collections():
    """Saari collections ki list nikaalte hain"""
    client = QdrantClient(url=QDRANT_URL)
    collections = client.get_collections().collections
    return [c.name for c in collections]


def get_collection_point_count(collection_name: str) -> int:
    """Return total points currently stored in a collection."""
    client = QdrantClient(url=QDRANT_URL)
    result = client.count(collection_name=collection_name, exact=True)
    return int(getattr(result, "count", 0) or 0)
