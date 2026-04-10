import os
import logging
import re
import socket
import multiprocessing as mp
import hashlib
import time
import html as html_lib
from collections import deque
from datetime import datetime, timezone
from ipaddress import ip_address
from queue import Empty
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse, urlunparse, urljoin
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
WEB_CRAWLER_MAX_SITEMAP_START_URLS = max(0, int(os.getenv("WEB_CRAWLER_MAX_SITEMAP_START_URLS", "120")))
DEFAULT_CHUNK_SIZE = max(200, int(os.getenv("RAG_CHUNK_SIZE", "1000")))
DEFAULT_CHUNK_OVERLAP = max(0, int(os.getenv("RAG_CHUNK_OVERLAP", "200")))
EMBED_UPLOAD_BATCH_SIZE = max(8, int(os.getenv("RAG_EMBED_UPLOAD_BATCH_SIZE", "64")))
PDF_OCR_DPI = max(120, int(os.getenv("PDF_OCR_DPI", "220")))
PDF_OCR_MAX_PAGES = max(1, int(os.getenv("PDF_OCR_MAX_PAGES", "80")))
PDF_OCR_LANG = os.getenv("PDF_OCR_LANG", "eng").strip() or "eng"

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


ProgressCallback = Optional[Callable[[str, Dict[str, Any]], None]]


def _emit_progress(progress_callback: ProgressCallback, event: str, **payload: Any) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(event, payload)
    except Exception:
        logger.debug("progress callback failed for event=%s", event, exc_info=True)


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


def _clean_scrapy_text_fragments(fragments: List[str]) -> str:
    cleaned: List[str] = []
    seen = set()
    boilerplate = {
        "cookie policy",
        "privacy policy",
        "terms of service",
        "accept all",
        "reject all",
        "subscribe",
        "menu",
        "search",
    }

    for fragment in fragments:
        normalized = re.sub(r"\s+", " ", (fragment or "").strip())
        if len(normalized) < 2:
            continue
        lowered = normalized.lower()
        if lowered in boilerplate:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(normalized)

    merged = " ".join(cleaned).strip()
    merged = re.sub(r"\s+", " ", merged)
    return merged[:200_000]


def _extract_clean_text_from_scrapy_response(response: Any) -> str:
    selector_candidates = [
        "//main//text()[normalize-space()]",
        "//article//text()[normalize-space()]",
        "//body//text()[normalize-space()]",
    ]

    fallback = ""
    for selector in selector_candidates:
        fragments = response.xpath(selector).getall()
        text = _clean_scrapy_text_fragments(fragments)
        if len(text) >= 200:
            return text
        if text and not fallback:
            fallback = text
    return fallback


def _extract_text_from_html_payload(html_payload: str) -> str:
    text = html_payload or ""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200_000]


def _extract_title_from_html_payload(html_payload: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_payload or "")
    if not match:
        return ""
    return re.sub(r"\s+", " ", html_lib.unescape(match.group(1) or "")).strip()[:280]


def _extract_links_from_html_payload(base_url: str, html_payload: str, allowed_host: str) -> List[str]:
    links: List[str] = []
    for href in re.findall(r'(?is)href=["\']([^"\']+)["\']', html_payload or ""):
        candidate = (href or "").strip()
        if not candidate:
            continue
        if candidate.startswith("#") or candidate.startswith("mailto:") or candidate.startswith("tel:"):
            continue
        absolute = urljoin(base_url, candidate)
        try:
            normalized = _normalize_url(absolute)
        except ValueError:
            continue
        parsed = urlparse(normalized)
        if (parsed.hostname or "").lower() != allowed_host:
            continue
        path = (parsed.path or "").lower()
        if path.endswith(_NON_HTML_EXTENSIONS):
            continue
        links.append(normalized)
    return links


def _extract_documents_via_requests(seed_url: str, max_pages: int, use_sitemap: bool) -> List[Document]:
    normalized_seed = _normalize_url(seed_url)
    parsed_seed = urlparse(normalized_seed)
    allowed_host = (parsed_seed.hostname or "").lower()
    if not allowed_host:
        return []

    queue_urls: deque[str] = deque([normalized_seed])
    if use_sitemap:
        sitemap_candidates = _discover_sitemap_urls(normalized_seed)
        max_from_sitemap = max(0, min(WEB_CRAWLER_MAX_SITEMAP_START_URLS, max_pages - 1))
        for item in sitemap_candidates[:max_from_sitemap]:
            if item not in queue_urls:
                queue_urls.append(item)

    visited: Set[str] = set()
    docs: List[Document] = []
    max_enqueued_urls = max(max_pages * 4, max_pages + 10)

    while queue_urls and len(visited) < max_enqueued_urls and len(docs) < max_pages:
        current_url = queue_urls.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            response = requests.get(
                current_url,
                timeout=WEB_CRAWLER_TIMEOUT_SECONDS,
                headers={"User-Agent": WEB_CRAWLER_USER_AGENT},
                allow_redirects=True,
            )
        except Exception:
            continue
        if int(response.status_code or 0) >= 400:
            continue
        content_type = str(response.headers.get("Content-Type", "")).lower()
        if content_type and ("text/html" not in content_type and "application/xhtml+xml" not in content_type):
            continue

        html_payload = response.text or ""
        text = _extract_text_from_html_payload(html_payload)
        title = _extract_title_from_html_payload(html_payload)
        if len(text) >= 200:
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": current_url,
                        "source_type": "website",
                        "title": title,
                    },
                )
            )

        if len(docs) >= max_pages:
            break

        links = _extract_links_from_html_payload(current_url, html_payload, allowed_host)
        for link in links:
            if link in visited:
                continue
            if len(queue_urls) + len(visited) >= max_enqueued_urls:
                break
            queue_urls.append(link)

    return docs


def _scrapy_crawl_worker(
    seed_url: str,
    max_pages: int,
    use_sitemap: bool,
    timeout_seconds: int,
    user_agent: str,
    output_queue: Any,
) -> None:
    try:
        from scrapy import Request, Spider
        from scrapy.crawler import CrawlerProcess
        from scrapy.linkextractors import LinkExtractor
        from scrapy.exceptions import CloseSpider
    except Exception as import_error:
        output_queue.put({"ok": False, "error": f"Scrapy import failed: {import_error}"})
        return

    allowed_host = (urlparse(seed_url).hostname or "").lower()
    deny_extensions = [ext.lstrip(".") for ext in _NON_HTML_EXTENSIONS]
    start_urls = [seed_url]
    if use_sitemap:
        sitemap_urls = _discover_sitemap_urls(seed_url)
        # Do not flood initial queue with giant sitemap lists.
        # Keep seeding proportional to max_pages so crawl finishes predictably.
        max_from_sitemap = max(0, min(WEB_CRAWLER_MAX_SITEMAP_START_URLS, max_pages - 1))
        if max_from_sitemap > 0:
            sitemap_urls = sitemap_urls[:max_from_sitemap]
        else:
            sitemap_urls = []
        for sitemap_url in sitemap_urls:
            if sitemap_url not in start_urls:
                start_urls.append(sitemap_url)

    collected_items: List[dict] = []
    blocked_root_status: Optional[int] = None
    extraction_error: Optional[str] = None

    class SiteTextSpider(Spider):
        name = "async_rag_site_text_spider"

        custom_settings = {
            "ROBOTSTXT_OBEY": True,
            "DOWNLOAD_TIMEOUT": timeout_seconds,
            "USER_AGENT": user_agent,
            "RETRY_TIMES": 1,
            "REDIRECT_ENABLED": True,
            "LOG_ENABLED": False,
            "TELNETCONSOLE_ENABLED": False,
        }

        def __init__(self) -> None:
            super().__init__()
            self.link_extractor = LinkExtractor(
                allow_domains=[allowed_host] if allowed_host else [],
                deny_extensions=deny_extensions,
                unique=True,
            )
            self.seen_urls: Set[str] = set()
            # Avoid unbounded queue growth on large internal link graphs.
            self.max_enqueued_urls = max(max_pages * 4, max_pages + 10)
            self.crawled_pages = 0

        def start_requests(self):
            for url in start_urls:
                yield Request(url=url, callback=self.parse_page, errback=self.parse_error, dont_filter=True)

        def parse_error(self, failure: Any):
            del failure
            return None

        def parse_page(self, response: Any):
            nonlocal blocked_root_status, extraction_error

            if len(collected_items) >= max_pages:
                raise CloseSpider("page_limit_reached")

            status_code = int(getattr(response, "status", 0) or 0)
            current_url = str(getattr(response, "url", "") or "")

            if current_url == seed_url and status_code in {401, 403, 429}:
                blocked_root_status = status_code
                return

            if status_code >= 400:
                return

            content_type = (response.headers.get("Content-Type", b"") or b"").decode("utf-8", errors="ignore").lower()
            if content_type and ("text/html" not in content_type and "application/xhtml+xml" not in content_type):
                return

            self.crawled_pages += 1
            if self.crawled_pages > max_pages:
                raise CloseSpider("crawl_page_limit_reached")

            try:
                text = _extract_clean_text_from_scrapy_response(response)
                title = _clean_scrapy_text_fragments(response.xpath("//title/text()").getall())
            except Exception as parse_error:
                extraction_error = str(parse_error)
                return

            if text:
                collected_items.append(
                    {
                        "source": current_url,
                        "title": title,
                        "text": text,
                    }
                )

            if len(collected_items) >= max_pages:
                raise CloseSpider("page_limit_reached")

            for link in self.link_extractor.extract_links(response):
                if len(self.seen_urls) >= self.max_enqueued_urls:
                    break
                try:
                    next_url = _normalize_url(link.url)
                except ValueError:
                    continue
                if next_url in self.seen_urls:
                    continue
                self.seen_urls.add(next_url)
                yield Request(url=next_url, callback=self.parse_page, errback=self.parse_error)

    try:
        process = CrawlerProcess(settings={"LOG_ENABLED": False})
        process.crawl(SiteTextSpider)
        process.start(stop_after_crawl=True, install_signal_handlers=False)
    except Exception as crawl_error:
        output_queue.put({"ok": False, "error": f"Scrapy crawl failed: {crawl_error}"})
        return

    output_queue.put(
        {
            "ok": True,
            "items": collected_items,
            "blocked_root_status": blocked_root_status,
            "extraction_error": extraction_error,
        }
    )


def _extract_documents_from_site(
    seed_url: str,
    max_pages: int,
    use_sitemap: bool,
    progress_callback: ProgressCallback = None,
) -> List[Document]:
    normalized_seed = _normalize_url(seed_url)
    if not _is_safe_public_host(normalized_seed):
        raise ValueError(f"Unsafe or non-public URL blocked: {seed_url}")

    ctx = mp.get_context("spawn")
    output_queue = ctx.Queue()
    crawl_proc = ctx.Process(
        target=_scrapy_crawl_worker,
        args=(
            normalized_seed,
            max_pages,
            use_sitemap,
            WEB_CRAWLER_TIMEOUT_SECONDS,
            WEB_CRAWLER_USER_AGENT,
            output_queue,
        ),
    )

    total_timeout = max(60, min(3600, WEB_CRAWLER_TIMEOUT_SECONDS * max_pages + 45))
    fallback_after_seconds = max(25, min(90, total_timeout // 3))
    crawl_proc.start()
    started_at = time.time()
    _emit_progress(
        progress_callback,
        "url_item_heartbeat",
        elapsed_seconds=0,
        timeout_seconds=total_timeout,
    )
    should_force_fallback = False
    fallback_reason = "scrapy_timeout"
    while crawl_proc.is_alive():
        elapsed = int(max(0, time.time() - started_at))
        if elapsed >= total_timeout:
            break
        if elapsed >= fallback_after_seconds:
            should_force_fallback = True
            fallback_reason = "scrapy_slow"
            break
        wait_slice = min(2.0, max(0.1, total_timeout - elapsed))
        crawl_proc.join(wait_slice)
        _emit_progress(
            progress_callback,
            "url_item_heartbeat",
            elapsed_seconds=int(max(0, time.time() - started_at)),
            timeout_seconds=total_timeout,
        )

    if crawl_proc.is_alive():
        crawl_proc.terminate()
        crawl_proc.join(5)
        _emit_progress(progress_callback, "url_fallback_start", reason=fallback_reason)
        logger.info("URL fallback triggered for %s (reason=%s)", normalized_seed, fallback_reason)
        fallback_docs = _extract_documents_via_requests(
            normalized_seed,
            max_pages=max_pages,
            use_sitemap=use_sitemap,
        )
        logger.info("URL fallback extracted %s docs for %s", len(fallback_docs), normalized_seed)
        if fallback_docs:
            _emit_progress(
                progress_callback,
                "url_fallback_done",
                method="requests",
                doc_count=len(fallback_docs),
            )
            return fallback_docs
        raise ValueError(f"Website crawl timed out for '{seed_url}'.")

    result = None
    try:
        result = output_queue.get_nowait()
    except Empty:
        result = None

    if not result:
        _emit_progress(progress_callback, "url_fallback_start", reason="scrapy_no_output")
        logger.info("URL fallback triggered for %s (reason=scrapy_no_output)", normalized_seed)
        fallback_docs = _extract_documents_via_requests(
            normalized_seed,
            max_pages=max_pages,
            use_sitemap=use_sitemap,
        )
        logger.info("URL fallback extracted %s docs for %s", len(fallback_docs), normalized_seed)
        if fallback_docs:
            _emit_progress(
                progress_callback,
                "url_fallback_done",
                method="requests",
                doc_count=len(fallback_docs),
            )
            return fallback_docs
        raise ValueError(f"Website crawl failed for '{seed_url}' with no crawler output.")

    if not result.get("ok"):
        raise ValueError(str(result.get("error") or f"Website crawl failed for '{seed_url}'."))

    blocked_root_status = result.get("blocked_root_status")
    if blocked_root_status in {401, 403, 429}:
        raise ValueError(
            f"Website blocked crawler access for '{seed_url}' (HTTP {blocked_root_status}). "
            "Whitelist this server IP/user-agent or provide publicly accessible pages."
        )

    extraction_error = result.get("extraction_error")
    if extraction_error and not result.get("items"):
        raise ValueError(f"Website crawl parsing failed for '{seed_url}': {extraction_error}")

    documents: List[Document] = []
    for item in result.get("items", []):
        text = (item.get("text") or "").strip()
        source = (item.get("source") or normalized_seed).strip()
        title = (item.get("title") or "").strip()
        if not text:
            continue
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": source,
                    "source_type": "website",
                    "title": title,
                },
            )
        )

    return documents


def _index_documents_to_collection(
    collection_name: str,
    documents: List[Document],
    force_recreate: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    progress_callback: ProgressCallback = None,
) -> int:
    if not GOOGLE_API_KEY:
        raise ValueError("Bhai, GOOGLE_API_KEY toh daal do!")

    _emit_progress(
        progress_callback,
        "embedding_prepare_start",
        collection_name=collection_name,
        document_count=len(documents),
    )
    embedding_model = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL_NAME)
    expected_dimension = get_embedding_dimension()
    ensure_qdrant_collection(
        collection_name=collection_name,
        vector_size=expected_dimension,
        force_recreate=force_recreate,
    )
    _emit_progress(
        progress_callback,
        "embedding_prepare_done",
        collection_name=collection_name,
        force_recreate=bool(force_recreate),
        expected_dimension=expected_dimension,
    )

    if not documents:
        _emit_progress(progress_callback, "no_documents", collection_name=collection_name)
        return 0

    safe_chunk_size = max(200, int(chunk_size))
    safe_chunk_overlap = max(0, min(int(chunk_overlap), safe_chunk_size - 1))
    _emit_progress(
        progress_callback,
        "chunking_start",
        collection_name=collection_name,
        document_count=len(documents),
        chunk_size=safe_chunk_size,
        chunk_overlap=safe_chunk_overlap,
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=safe_chunk_size,
        chunk_overlap=safe_chunk_overlap,
        separators=[
            "\n\n\n",
            "\n\n",
            "\n",
            ". ",
            "? ",
            "! ",
            "; ",
            ", ",
            " ",
        ],
    )
    raw_chunks = text_splitter.split_documents(documents)
    all_chunks = _prepare_chunks_with_metadata(raw_chunks, collection_name)
    _emit_progress(
        progress_callback,
        "chunking_done",
        collection_name=collection_name,
        document_count=len(documents),
        raw_chunk_count=len(raw_chunks),
        prepared_chunk_count=len(all_chunks),
    )

    if not all_chunks:
        _emit_progress(progress_callback, "no_chunks", collection_name=collection_name)
        return 0

    logger.info(f"Uploading {len(all_chunks)} chunks to: {collection_name}")
    total_chunks = len(all_chunks)
    total_batches = max(1, (total_chunks + EMBED_UPLOAD_BATCH_SIZE - 1) // EMBED_UPLOAD_BATCH_SIZE)
    _emit_progress(
        progress_callback,
        "embedding_upload_start",
        collection_name=collection_name,
        total_chunks=total_chunks,
        total_batches=total_batches,
        batch_size=EMBED_UPLOAD_BATCH_SIZE,
    )
    uploaded_chunks = 0
    for batch_index in range(total_batches):
        batch_start = batch_index * EMBED_UPLOAD_BATCH_SIZE
        batch_end = min(total_chunks, batch_start + EMBED_UPLOAD_BATCH_SIZE)
        chunk_batch = all_chunks[batch_start:batch_end]
        QdrantVectorStore.from_documents(
            documents=chunk_batch,
            embedding=embedding_model,
            url=QDRANT_URL,
            collection_name=collection_name,
        )
        uploaded_chunks = batch_end
        _emit_progress(
            progress_callback,
            "embedding_upload_batch_done",
            collection_name=collection_name,
            batch_index=batch_index + 1,
            total_batches=total_batches,
            uploaded_chunks=uploaded_chunks,
            total_chunks=total_chunks,
        )
    _emit_progress(
        progress_callback,
        "embedding_upload_done",
        collection_name=collection_name,
        total_chunks=total_chunks,
        total_batches=total_batches,
    )
    return len(all_chunks)


def _prepare_chunks_with_metadata(chunks: List[Document], collection_name: str) -> List[Document]:
    prepared: List[Document] = []
    seen_fingerprints: Set[str] = set()
    ingested_at = datetime.now(timezone.utc).isoformat()

    for idx, chunk in enumerate(chunks):
        text = re.sub(r"\s+", " ", (chunk.page_content or "")).strip()
        if len(text) < 40:
            continue

        fingerprint = hashlib.sha1(text.lower().encode("utf-8")).hexdigest()
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)

        metadata = dict(chunk.metadata or {})
        source = str(metadata.get("source") or metadata.get("file_path") or "unknown")
        source_type = str(metadata.get("source_type") or "unknown")
        title = str(metadata.get("title") or "")
        page = metadata.get("page_label", metadata.get("page", "N/A"))
        chunk_id_seed = f"{collection_name}|{source}|{page}|{idx}|{fingerprint[:16]}"
        chunk_id = hashlib.sha1(chunk_id_seed.encode("utf-8")).hexdigest()

        metadata.update(
            {
                "source": source,
                "source_type": source_type,
                "title": title,
                "page_label": str(page),
                "chunk_index": idx,
                "chunk_char_count": len(text),
                "chunk_token_estimate": max(1, len(text) // 4),
                "chunk_id": chunk_id,
                "ingested_at": ingested_at,
            }
        )

        chunk.page_content = text
        chunk.metadata = metadata
        prepared.append(chunk)

    return prepared

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


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _ocr_pdf_pages(file_path: str, page_numbers: List[int]) -> dict[int, str]:
    if not page_numbers:
        return {}

    try:
        import fitz
        import pytesseract
        from PIL import Image
    except Exception as import_error:
        raise ValueError(
            "OCR is enabled but OCR dependencies are missing. "
            "Install PyMuPDF, pytesseract, Pillow, and system package tesseract-ocr."
        ) from import_error

    extracted: dict[int, str] = {}
    requested_pages = sorted(set(int(p) for p in page_numbers if int(p) >= 0))
    if not requested_pages:
        return extracted

    logger.info(
        "OCR fallback start for %s (pages=%s dpi=%s lang=%s)",
        file_path,
        requested_pages[:12],
        PDF_OCR_DPI,
        PDF_OCR_LANG,
    )

    doc = fitz.open(file_path)
    try:
        max_pages = min(len(requested_pages), PDF_OCR_MAX_PAGES)
        dpi_scale = max(1.0, float(PDF_OCR_DPI) / 72.0)
        matrix = fitz.Matrix(dpi_scale, dpi_scale)

        for page_number in requested_pages[:max_pages]:
            if page_number >= len(doc):
                continue
            page = doc.load_page(page_number)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_mode = "RGB" if pix.n >= 3 else "L"
            image = Image.frombytes(image_mode, [pix.width, pix.height], pix.samples)
            text = _normalize_text(pytesseract.image_to_string(image, lang=PDF_OCR_LANG))
            if text:
                extracted[page_number] = text
    finally:
        doc.close()

    logger.info(
        "OCR fallback completed for %s: extracted pages=%s/%s",
        file_path,
        len(extracted),
        min(len(requested_pages), PDF_OCR_MAX_PAGES),
    )
    return extracted


def _load_pdf_documents(file_path: str, use_ocr: bool) -> List[Document]:
    loader = PyPDFLoader(file_path=file_path)
    docs = loader.load()
    for doc in docs:
        doc.metadata = {**doc.metadata, "source_type": "pdf"}

    if not docs:
        return []

    if not use_ocr:
        return docs

    texts_by_page: dict[int, str] = {}
    pages_for_ocr: List[int] = []
    for idx, doc in enumerate(docs):
        page_number = int((doc.metadata or {}).get("page", idx))
        text = _normalize_text(doc.page_content or "")
        if len(text) >= 40:
            texts_by_page[page_number] = text
        else:
            pages_for_ocr.append(page_number)

    ocr_text_by_page = _ocr_pdf_pages(file_path=file_path, page_numbers=pages_for_ocr)
    merged_docs: List[Document] = []
    for idx, doc in enumerate(docs):
        page_number = int((doc.metadata or {}).get("page", idx))
        merged_text = texts_by_page.get(page_number) or ocr_text_by_page.get(page_number) or ""
        merged_docs.append(
            Document(
                page_content=merged_text,
                metadata={**(doc.metadata or {}), "ocr_applied": bool(page_number in ocr_text_by_page)},
            )
        )
    return merged_docs


def index_pdfs_to_collection(
    collection_name: str,
    file_paths: List[str],
    force_recreate: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    use_ocr: bool = False,
    progress_callback: ProgressCallback = None,
):
    """PDFs ko read karke aur tukde-tukde karke Qdrant mein daalte hain (Gyan Ka Sagar)"""
    documents: List[Document] = []
    total_files = len(file_paths)
    _emit_progress(
        progress_callback,
        "pdf_loading_start",
        collection_name=collection_name,
        total_files=total_files,
        use_ocr=bool(use_ocr),
    )
    for index, file_path in enumerate(file_paths):
        logger.info(
            "File index ho rahi hai: %s (ocr=%s)",
            file_path,
            use_ocr,
        )
        _emit_progress(
            progress_callback,
            "pdf_file_start",
            collection_name=collection_name,
            index=index + 1,
            total=total_files,
            file_path=file_path,
        )
        docs = _load_pdf_documents(file_path=file_path, use_ocr=use_ocr)
        documents.extend(docs)
        _emit_progress(
            progress_callback,
            "pdf_file_done",
            collection_name=collection_name,
            index=index + 1,
            total=total_files,
            file_path=file_path,
            page_count=len(docs),
            document_count=len(documents),
        )
    _emit_progress(
        progress_callback,
        "pdf_loading_done",
        collection_name=collection_name,
        total_files=total_files,
        document_count=len(documents),
    )

    if not documents:
        logger.warning("PDF mein kuch kaam ka nahi mila bhai.")
        _emit_progress(progress_callback, "no_documents", collection_name=collection_name)
        return 0

    return _index_documents_to_collection(
        collection_name=collection_name,
        documents=documents,
        force_recreate=force_recreate,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        progress_callback=progress_callback,
    )


def index_urls_to_collection(
    collection_name: str,
    urls: List[str],
    force_recreate: bool = False,
    max_pages_per_site: Optional[int] = None,
    use_sitemap: Optional[bool] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    progress_callback: ProgressCallback = None,
) -> int:
    """Website URLs crawl karke Scrapy pipeline se clean text ko Qdrant collection mein index karo."""
    crawl_limit = max_pages_per_site or WEB_CRAWLER_MAX_PAGES_PER_SITE
    crawl_limit = max(1, crawl_limit)
    sitemap_mode = WEB_CRAWLER_USE_SITEMAP if use_sitemap is None else bool(use_sitemap)

    documents: List[Document] = []
    failures: List[str] = []
    total_urls = len(urls)
    _emit_progress(
        progress_callback,
        "url_crawl_start",
        collection_name=collection_name,
        total_urls=total_urls,
        max_pages_per_site=crawl_limit,
        use_sitemap=sitemap_mode,
    )
    for index, url in enumerate(urls):
        clean_url = (url or "").strip()
        if not clean_url:
            continue
        logger.info(f"Website crawl start (scrapy): {clean_url}")
        _emit_progress(
            progress_callback,
            "url_item_start",
            collection_name=collection_name,
            index=index + 1,
            total=total_urls,
            url=clean_url,
        )
        try:
            def _relay_extract_progress(event: str, payload: Dict[str, Any]) -> None:
                _emit_progress(
                    progress_callback,
                    event,
                    collection_name=collection_name,
                    index=index + 1,
                    total=total_urls,
                    url=clean_url,
                    **(payload or {}),
                )

            site_docs = _extract_documents_from_site(
                clean_url,
                max_pages=crawl_limit,
                use_sitemap=sitemap_mode,
                progress_callback=_relay_extract_progress,
            )
        except ValueError as e:
            failure = str(e)
            failures.append(failure)
            logger.warning(f"Website crawl validation failed for {clean_url}: {failure}")
            _emit_progress(
                progress_callback,
                "url_item_failed",
                collection_name=collection_name,
                index=index + 1,
                total=total_urls,
                url=clean_url,
                error=failure,
            )
            continue
        documents.extend(site_docs)
        _emit_progress(
            progress_callback,
            "url_item_done",
            collection_name=collection_name,
            index=index + 1,
            total=total_urls,
            url=clean_url,
            doc_count=len(site_docs),
            document_count=len(documents),
        )
    _emit_progress(
        progress_callback,
        "url_crawl_done",
        collection_name=collection_name,
        total_urls=total_urls,
        document_count=len(documents),
        failure_count=len(failures),
    )

    if not documents:
        if failures:
            _emit_progress(
                progress_callback,
                "url_crawl_failed",
                collection_name=collection_name,
                errors=failures,
            )
            raise ValueError(" ; ".join(failures))
        logger.warning("Website se koi crawlable content nahi mila.")
        _emit_progress(progress_callback, "no_documents", collection_name=collection_name)
        return 0

    return _index_documents_to_collection(
        collection_name=collection_name,
        documents=documents,
        force_recreate=force_recreate,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        progress_callback=progress_callback,
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
