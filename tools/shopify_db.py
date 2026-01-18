"""
Shopify Store Database - Store and manage Shopify stores and products
Uses PostgreSQL via SQLAlchemy
"""

import os
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Session, relationship
from sqlalchemy import select

DATABASE_URL = os.environ.get("DATABASE_URL")

class Base(DeclarativeBase):
    pass

class ShopifyStore(Base):
    __tablename__ = "shopify_stores"
    
    id = Column(Integer, primary_key=True)
    url = Column(String(500), unique=True, nullable=False)
    domain = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")
    storefront_token = Column(String(255), nullable=True)
    currency = Column(String(10), default="USD")
    country = Column(String(10), default="US")
    last_scan = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    products = relationship("ShopifyProduct", back_populates="store", cascade="all, delete-orphan")

class ShopifyProduct(Base):
    __tablename__ = "shopify_products"
    
    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("shopify_stores.id", ondelete="CASCADE"), nullable=False)
    variant_id = Column(String(100), nullable=False)
    title = Column(String(500), nullable=True)
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    available = Column(Boolean, default=True)
    last_seen = Column(DateTime, default=datetime.utcnow)
    
    store = relationship("ShopifyStore", back_populates="products")


class CachedCard(Base):
    """Cached approved cards for Auto Checkout"""
    __tablename__ = "cached_cards"
    
    id = Column(Integer, primary_key=True)
    card_number = Column(String(20), nullable=False)
    card_month = Column(String(2), nullable=False)
    card_year = Column(String(4), nullable=False)
    card_cvv = Column(String(4), nullable=False)
    bin_info = Column(String(100), nullable=True)
    bank_name = Column(String(200), nullable=True)
    card_type = Column(String(50), nullable=True)
    country = Column(String(50), nullable=True)
    last_gate = Column(String(100), nullable=True)
    times_used = Column(Integer, default=1)
    last_used = Column(DateTime, default=datetime.utcnow)
    added_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="active")

engine = None

def get_engine():
    global engine
    if engine is None and DATABASE_URL:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        Base.metadata.create_all(engine)
    return engine

def init_db():
    """Initialize database tables"""
    eng = get_engine()
    if eng:
        Base.metadata.create_all(eng)
        return True
    return False

def add_store(url: str) -> tuple:
    """Add a new store to the database. Returns (success, message)"""
    from urllib.parse import urlparse
    
    eng = get_engine()
    if not eng:
        return False, "Database not configured"
    
    parsed = urlparse(url if url.startswith("http") else f"https://{url}")
    domain = parsed.netloc or url.replace("https://", "").replace("http://", "").split("/")[0]
    normalized_url = f"https://{domain}"
    
    with Session(eng) as session:
        existing = session.execute(
            select(ShopifyStore).where(ShopifyStore.domain == domain)
        ).scalar_one_or_none()
        
        if existing:
            return False, f"Store already exists: {domain}"
        
        store = ShopifyStore(
            url=normalized_url,
            domain=domain,
            status="pending"
        )
        session.add(store)
        session.commit()
        return True, f"Added store: {domain}"

def remove_store(identifier: str) -> tuple:
    """Remove a store by ID or domain. Returns (success, message)"""
    eng = get_engine()
    if not eng:
        return False, "Database not configured"
    
    with Session(eng) as session:
        store = None
        if identifier.isdigit():
            store = session.get(ShopifyStore, int(identifier))
        else:
            domain = identifier.replace("https://", "").replace("http://", "").split("/")[0]
            store = session.execute(
                select(ShopifyStore).where(ShopifyStore.domain == domain)
            ).scalar_one_or_none()
        
        if not store:
            return False, f"Store not found: {identifier}"
        
        domain = store.domain
        session.delete(store)
        session.commit()
        return True, f"Removed store: {domain}"

def list_stores() -> list:
    """List all stores with their status and product count"""
    eng = get_engine()
    if not eng:
        return []
    
    with Session(eng) as session:
        stores = session.execute(select(ShopifyStore)).scalars().all()
        result = []
        for store in stores:
            product_count = len([p for p in store.products if p.available])
            result.append({
                "id": store.id,
                "domain": store.domain,
                "status": store.status,
                "products": product_count,
                "last_scan": store.last_scan,
                "currency": store.currency,
            })
        return result

def get_store_with_products(domain: str = None, store_id: int = None) -> dict:
    """Get a store with its cached products"""
    eng = get_engine()
    if not eng:
        return None
    
    with Session(eng) as session:
        if store_id:
            store = session.get(ShopifyStore, store_id)
        elif domain:
            domain_clean = domain.replace("https://", "").replace("http://", "").split("/")[0]
            store = session.execute(
                select(ShopifyStore).where(ShopifyStore.domain == domain_clean)
            ).scalar_one_or_none()
        else:
            return None
        
        if not store:
            return None
        
        available_products = [p for p in store.products if p.available]
        cheapest = min(available_products, key=lambda p: p.price) if available_products else None
        
        return {
            "id": store.id,
            "domain": store.domain,
            "url": store.url,
            "storefront_token": store.storefront_token,
            "currency": store.currency,
            "country": store.country,
            "last_scan": store.last_scan,
            "status": store.status,
            "cheapest_product": {
                "variant_id": cheapest.variant_id,
                "price": cheapest.price,
                "title": cheapest.title,
                "currency": cheapest.currency,
            } if cheapest else None,
            "product_count": len(available_products),
        }

def get_random_store_with_product() -> dict:
    """Get a random store that has available products"""
    eng = get_engine()
    if not eng:
        return None
    
    with Session(eng) as session:
        stores = session.execute(
            select(ShopifyStore).where(ShopifyStore.status == "ready")
        ).scalars().all()
        
        ready_stores = []
        for store in stores:
            available = [p for p in store.products if p.available]
            if available:
                cheapest = min(available, key=lambda p: p.price)
                ready_stores.append({
                    "id": store.id,
                    "domain": store.domain,
                    "url": store.url,
                    "storefront_token": store.storefront_token,
                    "currency": store.currency,
                    "country": store.country,
                    "cheapest_product": {
                        "variant_id": cheapest.variant_id,
                        "price": cheapest.price,
                        "title": cheapest.title,
                    }
                })
        
        if not ready_stores:
            return None
        
        import random
        return random.choice(ready_stores)

def update_store_products(store_id: int, products: list, storefront_token: str = None, currency: str = None, country: str = None):
    """Update products for a store after discovery"""
    eng = get_engine()
    if not eng:
        return False
    
    with Session(eng) as session:
        store = session.get(ShopifyStore, store_id)
        if not store:
            return False
        
        for product in store.products:
            session.delete(product)
        
        for prod in products:
            new_product = ShopifyProduct(
                store_id=store_id,
                variant_id=str(prod["variant_id"]),
                title=prod.get("title", "Unknown"),
                price=prod["price"],
                currency=prod.get("currency", currency or "USD"),
                available=prod.get("available", True),
            )
            session.add(new_product)
        
        store.status = "ready" if products else "empty"
        store.last_scan = datetime.utcnow()
        store.error_count = 0
        store.last_error = None
        
        if storefront_token:
            store.storefront_token = storefront_token
        if currency:
            store.currency = currency
        if country:
            store.country = country
        
        session.commit()
        return True

MAX_ERROR_COUNT = 5

def mark_store_error(store_id: int, error: str):
    """Mark a store as having an error. Quarantine after MAX_ERROR_COUNT failures."""
    eng = get_engine()
    if not eng:
        return
    
    with Session(eng) as session:
        store = session.get(ShopifyStore, store_id)
        if store:
            store.error_count += 1
            store.last_error = error[:500]
            if store.error_count >= MAX_ERROR_COUNT:
                store.status = "quarantined"
            elif store.error_count >= 3:
                store.status = "error"
            else:
                store.status = "pending"
            store.last_scan = datetime.utcnow()
            session.commit()


def is_store_quarantined(domain: str) -> bool:
    """Check if a store is quarantined due to repeated failures"""
    eng = get_engine()
    if not eng:
        return False
    
    domain_clean = domain.replace("https://", "").replace("http://", "").split("/")[0].lower()
    
    with Session(eng) as session:
        store = session.execute(
            select(ShopifyStore).where(ShopifyStore.domain == domain_clean)
        ).scalar_one_or_none()
        
        if store and store.status == "quarantined":
            return True
        if store and store.error_count >= MAX_ERROR_COUNT:
            return True
    return False

def get_stores_to_scan(limit: int = 10) -> list:
    """Get stores that need scanning (pending or stale)"""
    eng = get_engine()
    if not eng:
        return []
    
    stale_threshold = datetime.utcnow() - timedelta(hours=24)
    
    with Session(eng) as session:
        stores = session.execute(
            select(ShopifyStore).where(
                (ShopifyStore.status == "pending") |
                (ShopifyStore.last_scan < stale_threshold) |
                (ShopifyStore.last_scan == None)
            ).limit(limit)
        ).scalars().all()
        
        return [{"id": s.id, "domain": s.domain, "url": s.url} for s in stores]

def count_stores() -> dict:
    """Get store statistics"""
    eng = get_engine()
    if not eng:
        return {"total": 0, "ready": 0, "pending": 0, "error": 0, "quarantined": 0}
    
    with Session(eng) as session:
        total = session.execute(select(ShopifyStore)).scalars().all()
        ready = [s for s in total if s.status == "ready"]
        pending = [s for s in total if s.status == "pending"]
        error = [s for s in total if s.status == "error"]
        quarantined = [s for s in total if s.status == "quarantined"]
        
        return {
            "total": len(total),
            "ready": len(ready),
            "pending": len(pending),
            "error": len(error),
            "quarantined": len(quarantined),
        }


def get_ready_store_urls() -> list:
    """Get URLs of all ready stores with products"""
    eng = get_engine()
    if not eng:
        return []
    
    with Session(eng) as session:
        stores = session.execute(
            select(ShopifyStore).where(ShopifyStore.status == "ready")
        ).scalars().all()
        
        ready_urls = []
        for store in stores:
            if store.products and len([p for p in store.products if p.available]) > 0:
                ready_urls.append(store.url)
        
        return ready_urls


def add_stores_bulk(urls: list, batch_size: int = 500) -> dict:
    """
    Add multiple stores at once with deduplication and batched commits
    Uses optimized batching for faster insertion
    Returns dict with added, skipped, errors counts
    """
    from urllib.parse import urlparse
    
    eng = get_engine()
    if not eng:
        return {"added": 0, "skipped": 0, "errors": 0, "message": "Database not configured"}
    
    added = 0
    skipped = 0
    errors = 0
    
    seen_domains = set()
    stores_to_add = []
    
    with Session(eng) as session:
        existing = session.execute(select(ShopifyStore.domain)).scalars().all()
        existing_domains = set(existing)
        
        for url in urls:
            url = url.strip()
            if not url or url.startswith('#'):
                continue
            
            try:
                parsed = urlparse(url if url.startswith("http") else f"https://{url}")
                domain = parsed.netloc or url.replace("https://", "").replace("http://", "").split("/")[0]
                domain = domain.lower().strip()
                
                if not domain or len(domain) < 4:
                    errors += 1
                    continue
                
                if domain in existing_domains or domain in seen_domains:
                    skipped += 1
                    continue
                
                normalized_url = f"https://{domain}"
                
                stores_to_add.append(ShopifyStore(
                    url=normalized_url,
                    domain=domain,
                    status="pending"
                ))
                seen_domains.add(domain)
                added += 1
                
            except Exception:
                errors += 1
        
        for i in range(0, len(stores_to_add), batch_size):
            batch = stores_to_add[i:i + batch_size]
            session.add_all(batch)
            session.commit()
    
    return {
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "message": f"Added {added} stores, skipped {skipped} duplicates, {errors} errors"
    }


async def add_stores_bulk_async(urls: list, batch_size: int = 500, progress_callback=None) -> dict:
    """
    Async version of add_stores_bulk with progress callbacks
    Non-blocking - allows bot to remain responsive during bulk operations
    """
    import asyncio
    from urllib.parse import urlparse
    
    eng = get_engine()
    if not eng:
        return {"added": 0, "skipped": 0, "errors": 0, "message": "Database not configured"}
    
    added = 0
    skipped = 0
    errors = 0
    total = len(urls)
    
    seen_domains = set()
    stores_to_add = []
    
    def _get_existing_domains():
        with Session(eng) as session:
            return set(session.execute(select(ShopifyStore.domain)).scalars().all())
    
    existing_domains = await asyncio.to_thread(_get_existing_domains)
    
    for idx, url in enumerate(urls):
        url = url.strip()
        if not url or url.startswith('#'):
            continue
        
        try:
            parsed = urlparse(url if url.startswith("http") else f"https://{url}")
            domain = parsed.netloc or url.replace("https://", "").replace("http://", "").split("/")[0]
            domain = domain.lower().strip()
            
            if not domain or len(domain) < 4:
                errors += 1
                continue
            
            if domain in existing_domains or domain in seen_domains:
                skipped += 1
                continue
            
            stores_to_add.append({
                "url": f"https://{domain}",
                "domain": domain,
            })
            seen_domains.add(domain)
            added += 1
            
        except Exception:
            errors += 1
        
        if progress_callback and (idx + 1) % 100 == 0:
            try:
                await progress_callback(idx + 1, total, "parsing")
            except:
                pass
        
        if (idx + 1) % 50 == 0:
            await asyncio.sleep(0)
    
    async def commit_batch(batch_stores):
        def _commit():
            with Session(eng) as session:
                for s in batch_stores:
                    store = ShopifyStore(
                        url=s["url"],
                        domain=s["domain"],
                        status="pending"
                    )
                    session.add(store)
                session.commit()
        await asyncio.to_thread(_commit)
    
    for i in range(0, len(stores_to_add), batch_size):
        batch = stores_to_add[i:i + batch_size]
        await commit_batch(batch)
        
        if progress_callback:
            try:
                await progress_callback(min(i + batch_size, len(stores_to_add)), len(stores_to_add), "committing")
            except:
                pass
        
        await asyncio.sleep(0)
    
    return {
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "message": f"Added {added} stores, skipped {skipped} duplicates, {errors} errors"
    }


def list_stores_full() -> list:
    """List all stores with their full product details (no truncation)"""
    eng = get_engine()
    if not eng:
        return []
    
    with Session(eng) as session:
        stores = session.execute(select(ShopifyStore)).scalars().all()
        result = []
        for store in stores:
            available_products = [p for p in store.products if p.available]
            cheapest = min(available_products, key=lambda p: p.price) if available_products else None
            
            result.append({
                "id": store.id,
                "domain": store.domain,
                "url": store.url,
                "status": store.status,
                "product_count": len(available_products),
                "last_scan": store.last_scan,
                "currency": store.currency,
                "country": store.country,
                "storefront_token": store.storefront_token,
                "cheapest_product": {
                    "variant_id": cheapest.variant_id,
                    "title": cheapest.title,
                    "price": cheapest.price,
                    "currency": cheapest.currency,
                } if cheapest else None,
                "all_products": [
                    {
                        "variant_id": p.variant_id,
                        "title": p.title,
                        "price": p.price,
                        "currency": p.currency,
                    } for p in available_products
                ] if available_products else [],
            })
        return result

def get_all_pending_store_ids() -> list:
    """Get all pending store IDs for bulk scanning"""
    eng = get_engine()
    if not eng:
        return []
    
    with Session(eng) as session:
        stores = session.execute(
            select(ShopifyStore).where(ShopifyStore.status == "pending")
        ).scalars().all()
        return [{"id": s.id, "domain": s.domain, "url": s.url} for s in stores]


def get_all_stores_for_scanning(include_quarantined: bool = False) -> list:
    """Get stores from database for scanning (excludes quarantined by default)"""
    eng = get_engine()
    if not eng:
        return []
    
    with Session(eng) as session:
        if include_quarantined:
            stores = session.execute(select(ShopifyStore)).scalars().all()
        else:
            stores = session.execute(
                select(ShopifyStore).where(ShopifyStore.status != "quarantined")
            ).scalars().all()
        return [s.url for s in stores]


def update_store_status(domain: str, status: str, stripe_pk: str = None):
    """Update a store's status and optionally store Stripe key"""
    eng = get_engine()
    if not eng:
        return False
    
    domain_clean = domain.replace("https://", "").replace("http://", "").split("/")[0].lower()
    
    with Session(eng) as session:
        store = session.execute(
            select(ShopifyStore).where(ShopifyStore.domain == domain_clean)
        ).scalar_one_or_none()
        
        if store:
            store.status = status
            store.last_scan = datetime.utcnow()
            if stripe_pk:
                store.storefront_token = stripe_pk
            session.commit()
            return True
    return False


def reset_all_stores_to_pending():
    """Reset all stores to pending status for re-scanning"""
    eng = get_engine()
    if not eng:
        return 0
    
    with Session(eng) as session:
        result = session.execute(select(ShopifyStore)).scalars().all()
        count = 0
        for store in result:
            store.status = "pending"
            store.last_scan = None
            count += 1
        session.commit()
        return count


def cache_card(card_num: str, card_mon: str, card_yer: str, card_cvv: str, 
               gate_name: str = None, bin_info: str = None, bank_name: str = None,
               card_type: str = None, country: str = None) -> tuple:
    """
    Cache an approved card to the database
    Returns (success, message, card_id)
    """
    eng = get_engine()
    if not eng:
        return False, "Database not configured", None
    
    card_yer_full = card_yer if len(card_yer) == 4 else f"20{card_yer}"
    
    with Session(eng) as session:
        existing = session.execute(
            select(CachedCard).where(
                CachedCard.card_number == card_num,
                CachedCard.card_cvv == card_cvv
            )
        ).scalar_one_or_none()
        
        if existing:
            existing.times_used += 1
            existing.last_used = datetime.utcnow()
            existing.last_gate = gate_name
            if bin_info:
                existing.bin_info = bin_info
            if bank_name:
                existing.bank_name = bank_name
            session.commit()
            return True, f"Card updated (used {existing.times_used}x)", existing.id
        
        card = CachedCard(
            card_number=card_num,
            card_month=card_mon.zfill(2),
            card_year=card_yer_full,
            card_cvv=card_cvv,
            bin_info=bin_info,
            bank_name=bank_name,
            card_type=card_type,
            country=country,
            last_gate=gate_name,
        )
        session.add(card)
        session.commit()
        return True, f"Card cached: {card_num[:6]}...{card_num[-4:]}", card.id


def get_all_cached_cards(status: str = "active") -> list:
    """Get all cached cards"""
    eng = get_engine()
    if not eng:
        return []
    
    with Session(eng) as session:
        cards = session.execute(
            select(CachedCard).where(CachedCard.status == status).order_by(CachedCard.last_used.desc())
        ).scalars().all()
        
        return [{
            "id": c.id,
            "card": f"{c.card_number}|{c.card_month}|{c.card_year[-2:]}|{c.card_cvv}",
            "card_masked": f"{c.card_number[:6]}****{c.card_number[-4:]}",
            "bin": c.card_number[:6],
            "bank": c.bank_name,
            "type": c.card_type,
            "country": c.country,
            "times_used": c.times_used,
            "last_gate": c.last_gate,
            "added": c.added_at,
        } for c in cards]


def remove_cached_card(identifier: str) -> tuple:
    """Remove a cached card by ID or last4"""
    eng = get_engine()
    if not eng:
        return False, "Database not configured"
    
    with Session(eng) as session:
        card = None
        if identifier.isdigit():
            card = session.get(CachedCard, int(identifier))
        else:
            card = session.execute(
                select(CachedCard).where(CachedCard.card_number.endswith(identifier[-4:]))
            ).scalar_one_or_none()
        
        if not card:
            return False, f"Card not found: {identifier}"
        
        masked = f"{card.card_number[:6]}****{card.card_number[-4:]}"
        session.delete(card)
        session.commit()
        return True, f"Removed: {masked}"


def mark_card_declined(card_id: int):
    """Mark a cached card as declined (after failed checkout)"""
    eng = get_engine()
    if not eng:
        return
    
    with Session(eng) as session:
        card = session.get(CachedCard, card_id)
        if card:
            card.status = "declined"
            session.commit()


def count_cached_cards() -> dict:
    """Get card cache statistics"""
    eng = get_engine()
    if not eng:
        return {"total": 0, "active": 0, "declined": 0}
    
    with Session(eng) as session:
        all_cards = session.execute(select(CachedCard)).scalars().all()
        active = [c for c in all_cards if c.status == "active"]
        declined = [c for c in all_cards if c.status == "declined"]
        
        return {
            "total": len(all_cards),
            "active": len(active),
            "declined": len(declined),
        }
