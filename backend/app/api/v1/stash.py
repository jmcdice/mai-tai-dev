"""StashAI API endpoints - personal link manager."""

import ipaddress
import logging
import re
import socket
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.stash_link import StashLink
from app.models.user import User
from app.schemas.stash import (
    StashLinkCreate,
    StashLinkListResponse,
    StashLinkResponse,
    StashLinkUpdate,
    UrlMetadata,
)
from app.services.ai import PROVIDER_MODELS, enrich_link

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stash", tags=["stash"])


def _validate_url(url: str) -> str:
    """Validate URL to prevent SSRF attacks.

    Only allows http/https schemes and blocks requests to private/internal IPs.
    Returns the validated URL or raises HTTPException.
    """
    parsed = urlparse(url)

    # Only allow http and https
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only http and https URLs are allowed",
        )

    if not parsed.hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL: no hostname",
        )

    # Resolve hostname and check for private IPs
    try:
        resolved = socket.getaddrinfo(parsed.hostname, None)
        for _, _, _, _, addr in resolved:
            ip = ipaddress.ip_address(addr[0])
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="URLs pointing to private/internal addresses are not allowed",
                )
    except socket.gaierror:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not resolve hostname",
        )

    return url

# Regex patterns for OG tag extraction
_OG_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_OG_TITLE_ALT = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', re.I)
_OG_DESC = re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_OG_DESC_ALT = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']', re.I)
_OG_IMAGE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_OG_IMAGE_ALT = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I)
_TITLE_TAG = re.compile(r'<title[^>]*>([^<]+)</title>', re.I)
_META_DESC = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_META_DESC_ALT = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', re.I)


def _first_match(*patterns, html: str) -> str | None:
    for pat in patterns:
        m = pat.search(html)
        if m:
            return m.group(1).strip()
    return None


async def _fetch_tweet_metadata(url: str) -> UrlMetadata | None:
    """Fetch tweet content via vxtwitter API for x.com/twitter.com links."""
    try:
        # Extract username and tweet ID from URL
        m = re.match(r'https?://(?:x\.com|twitter\.com)/(\w+)/status/(\d+)', url)
        if not m:
            return None
        username, tweet_id = m.group(1), m.group(2)
        api_url = f"https://api.vxtwitter.com/{username}/status/{tweet_id}"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(api_url)
            resp.raise_for_status()
            data = resp.json()

        user_name = data.get("user_name", username)
        text = data.get("text", "")
        thumbnail = None
        media_urls = data.get("mediaURLs", [])
        if media_urls:
            thumbnail = media_urls[0]

        return UrlMetadata(
            url=url,
            title=f"@{data.get('user_screen_name', username)}: {text[:100]}",
            description=f"{user_name} (@{data.get('user_screen_name', username)}): {text}",
            thumbnail_url=thumbnail,
        )
    except Exception:
        return None


async def _fetch_url_metadata(url: str) -> UrlMetadata:
    """Fetch a URL and extract OG metadata."""
    # Special handling for x.com / twitter.com links
    if re.match(r'https?://(?:x\.com|twitter\.com)/\w+/status/\d+', url):
        tweet_meta = await _fetch_tweet_metadata(url)
        if tweet_meta:
            return tweet_meta

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; StashAI/1.0; +https://github.com/jmcdice/mai-tai-dev)",
            "Accept": "text/html,application/xhtml+xml",
        }
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

        title = _first_match(_OG_TITLE, _OG_TITLE_ALT, _TITLE_TAG, html=html)
        description = _first_match(_OG_DESC, _OG_DESC_ALT, _META_DESC, _META_DESC_ALT, html=html)
        thumbnail_url = _first_match(_OG_IMAGE, _OG_IMAGE_ALT, html=html)

        return UrlMetadata(
            url=url,
            title=title,
            description=description[:500] if description else None,
            thumbnail_url=thumbnail_url,
        )
    except Exception:
        return UrlMetadata(url=url)


@router.get("/fetch-metadata", response_model=UrlMetadata)
async def fetch_metadata(
    url: str = Query(..., description="URL to fetch metadata for"),
    current_user: User = Depends(get_current_user),
) -> UrlMetadata:
    """Fetch OG metadata for a URL without saving it."""
    _validate_url(url)
    return await _fetch_url_metadata(url)


@router.get("/ai-models")
async def get_ai_models(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return available AI providers and their models."""
    return {"providers": PROVIDER_MODELS}


@router.post("", response_model=StashLinkResponse, status_code=status.HTTP_201_CREATED)
async def create_link(
    data: StashLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StashLink:
    """Save a link to the stash. Auto-fetches metadata if title not provided."""
    _validate_url(data.url)
    title = data.title
    description = data.description
    thumbnail_url = data.thumbnail_url

    # Auto-fetch metadata if title not provided
    if not title:
        meta = await _fetch_url_metadata(data.url)
        title = meta.title
        description = description or meta.description
        thumbnail_url = thumbnail_url or meta.thumbnail_url

    link = StashLink(
        user_id=current_user.id,
        url=data.url,
        title=title,
        description=description,
        thumbnail_url=thumbnail_url,
        tags=data.tags,
        notes=data.notes,
        status="unread",
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    # AI enrichment — if user has LLM settings configured
    settings = current_user.settings or {}
    llm_provider = settings.get("stash_llm_provider")
    llm_model = settings.get("stash_llm_model")
    llm_api_key = settings.get("stash_llm_api_key")

    if llm_provider and llm_model and llm_api_key:
        try:
            enriched = await enrich_link(
                url=link.url,
                title=title,
                description=description,
                provider=llm_provider,
                model=llm_model,
                api_key=llm_api_key,
                ollama_base_url=settings.get("stash_ollama_base_url"),
            )
            if enriched:
                if "title" in enriched:
                    link.ai_title = enriched["title"]
                if "summary" in enriched:
                    link.summary = enriched["summary"]
                if "tags" in enriched:
                    link.ai_tags = enriched["tags"]
                    # Merge AI tags with user-provided tags (no duplicates)
                    existing = set(link.tags or [])
                    new_tags = [t for t in enriched["tags"] if t not in existing]
                    if new_tags:
                        link.tags = list(existing) + new_tags
                await db.commit()
                await db.refresh(link)
        except Exception as e:
            logger.warning(f"AI enrichment failed for link {link.id}: {e}")

    return link


@router.get("", response_model=StashLinkListResponse)
async def list_links(
    status: str | None = Query(None, description="Filter by status: unread, read, archived"),
    tag: str | None = Query(None, description="Filter by tag"),
    q: str | None = Query(None, description="Search in title, description, url"),
    limit: int = Query(50, le=200, ge=1),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List stash links for the current user."""
    query = select(StashLink).where(StashLink.user_id == current_user.id)

    if status:
        query = query.where(StashLink.status == status)
    if tag:
        query = query.where(StashLink.tags.contains([tag]))
    if q:
        search = f"%{q}%"
        from sqlalchemy import or_
        query = query.where(
            or_(
                StashLink.title.ilike(search),
                StashLink.description.ilike(search),
                StashLink.url.ilike(search),
            )
        )

    query = query.order_by(StashLink.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    links = result.scalars().all()

    # Count total
    from sqlalchemy import func
    count_query = select(func.count()).select_from(StashLink).where(StashLink.user_id == current_user.id)
    if status:
        count_query = count_query.where(StashLink.status == status)
    if tag:
        count_query = count_query.where(StashLink.tags.contains([tag]))
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    return {"links": links, "total": total}


@router.get("/{link_id}", response_model=StashLinkResponse)
async def get_link(
    link_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StashLink:
    """Get a single stash link."""
    result = await db.execute(
        select(StashLink).where(StashLink.id == link_id, StashLink.user_id == current_user.id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return link


@router.patch("/{link_id}", response_model=StashLinkResponse)
async def update_link(
    link_id: UUID,
    data: StashLinkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StashLink:
    """Update a stash link."""
    result = await db.execute(
        select(StashLink).where(StashLink.id == link_id, StashLink.user_id == current_user.id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if data.title is not None:
        link.title = data.title
    if data.description is not None:
        link.description = data.description
    if data.thumbnail_url is not None:
        link.thumbnail_url = data.thumbnail_url
    if data.tags is not None:
        link.tags = data.tags
    if data.status is not None:
        link.status = data.status
    if data.notes is not None:
        link.notes = data.notes
    link.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(link)
    return link


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    link_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a stash link."""
    result = await db.execute(
        select(StashLink).where(StashLink.id == link_id, StashLink.user_id == current_user.id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()
