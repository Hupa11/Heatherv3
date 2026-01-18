"""
Smart Routing Module - BIN-based store selection, price filtering, and intelligent fallback
Routes cards to optimal stores based on historical success patterns
"""

import time
import random
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class BINStats:
    """Statistics for a specific BIN on a specific store"""
    bin_prefix: str
    store_domain: str
    total_checks: int = 0
    successes: int = 0
    failures: int = 0
    last_check: float = 0.0
    decline_reasons: Dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        if self.total_checks == 0:
            return 0.5
        return self.successes / self.total_checks
    
    @property
    def is_blocked(self) -> bool:
        """Check if this BIN appears to be blocked on this store"""
        if self.total_checks < 3:
            return False
        return self.success_rate < 0.1


class BINRouter:
    """
    Routes cards to optimal stores based on BIN success patterns.
    Tracks which BIN ranges work on which stores.
    """
    
    def __init__(self):
        self._bin_stats: Dict[str, BINStats] = {}
        self._blocked_combinations: Set[Tuple[str, str]] = set()
    
    def _get_bin_prefix(self, card_num: str) -> str:
        """Extract BIN prefix (first 6 digits)"""
        return card_num[:6] if len(card_num) >= 6 else card_num
    
    def _make_key(self, bin_prefix: str, store_domain: str) -> str:
        """Create unique key for BIN+store combination"""
        return f"{bin_prefix}:{store_domain}"
    
    def get_best_store(
        self, 
        card_num: str, 
        available_stores: List[str],
        min_success_rate: float = 0.2
    ) -> Optional[str]:
        """
        Get the best store for a specific card BIN.
        
        Args:
            card_num: Card number to check
            available_stores: List of available store domains
            min_success_rate: Minimum success rate to consider
        
        Returns:
            Best store domain or None if all blocked
        """
        bin_prefix = self._get_bin_prefix(card_num)
        
        candidates = []
        unknown_stores = []
        
        for store in available_stores:
            if (bin_prefix, store) in self._blocked_combinations:
                continue
            
            key = self._make_key(bin_prefix, store)
            
            if key in self._bin_stats:
                stats = self._bin_stats[key]
                if stats.success_rate >= min_success_rate:
                    candidates.append((store, stats.success_rate))
            else:
                unknown_stores.append(store)
        
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            top_rate = candidates[0][1]
            top_candidates = [s for s, r in candidates if r >= top_rate * 0.8]
            return random.choice(top_candidates)
        
        if unknown_stores:
            return random.choice(unknown_stores)
        
        if available_stores:
            return random.choice(available_stores)
        
        return None
    
    def record_result(
        self, 
        card_num: str, 
        store_domain: str, 
        success: bool,
        decline_reason: str = ""
    ) -> None:
        """Record check result for BIN+store combination"""
        bin_prefix = self._get_bin_prefix(card_num)
        key = self._make_key(bin_prefix, store_domain)
        
        if key not in self._bin_stats:
            self._bin_stats[key] = BINStats(
                bin_prefix=bin_prefix,
                store_domain=store_domain
            )
        
        stats = self._bin_stats[key]
        stats.total_checks += 1
        stats.last_check = time.time()
        
        if success:
            stats.successes += 1
        else:
            stats.failures += 1
            if decline_reason:
                stats.decline_reasons[decline_reason] = stats.decline_reasons.get(decline_reason, 0) + 1
        
        if stats.is_blocked:
            self._blocked_combinations.add((bin_prefix, store_domain))
    
    def get_bin_report(self, card_num: str) -> Dict[str, Dict]:
        """Get success rates for a BIN across all known stores"""
        bin_prefix = self._get_bin_prefix(card_num)
        report = {}
        
        for key, stats in self._bin_stats.items():
            if stats.bin_prefix == bin_prefix:
                report[stats.store_domain] = {
                    "success_rate": f"{stats.success_rate * 100:.1f}%",
                    "total_checks": stats.total_checks,
                    "is_blocked": stats.is_blocked,
                }
        
        return report
    
    def clear_old_data(self, max_age: float = 86400) -> int:
        """Clear data older than max_age seconds"""
        now = time.time()
        old_keys = [k for k, s in self._bin_stats.items() if now - s.last_check > max_age]
        for key in old_keys:
            stats = self._bin_stats.pop(key)
            self._blocked_combinations.discard((stats.bin_prefix, stats.store_domain))
        return len(old_keys)


class PriceFilter:
    """
    Filters stores based on product price ranges.
    Some fraud detection flags very low or very high prices.
    """
    
    def __init__(self, min_price: float = 1.0, max_price: float = 100.0):
        self.min_price = min_price
        self.max_price = max_price
    
    def filter_stores(
        self, 
        stores: List[Dict],
        min_price: float = None,
        max_price: float = None
    ) -> List[Dict]:
        """
        Filter stores by product price range.
        
        Args:
            stores: List of store dicts with 'price' field
            min_price: Minimum price (overrides default)
            max_price: Maximum price (overrides default)
        
        Returns:
            Filtered list of stores
        """
        min_p = min_price if min_price is not None else self.min_price
        max_p = max_price if max_price is not None else self.max_price
        
        filtered = []
        for store in stores:
            price = store.get("price", 0)
            if isinstance(price, str):
                try:
                    price = float(price.replace("$", "").replace(",", ""))
                except (ValueError, TypeError):
                    continue
            
            if min_p <= price <= max_p:
                filtered.append(store)
        
        return filtered
    
    def set_range(self, min_price: float, max_price: float) -> None:
        """Update price range"""
        self.min_price = min_price
        self.max_price = max_price


class ParallelFallback:
    """
    Manages parallel store fallback when primary store fails mid-checkout.
    Automatically retries on backup store without full restart.
    """
    
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._last_failure: Dict[str, float] = {}
    
    def get_fallback_stores(
        self, 
        failed_store: str, 
        all_stores: List[str],
        exclude: List[str] = None
    ) -> List[str]:
        """
        Get list of fallback stores after primary fails.
        
        Args:
            failed_store: Store that just failed
            all_stores: All available stores
            exclude: Additional stores to exclude
        
        Returns:
            List of fallback stores sorted by reliability
        """
        exclude_set = {failed_store}
        if exclude:
            exclude_set.update(exclude)
        
        candidates = [s for s in all_stores if s not in exclude_set]
        
        candidates.sort(key=lambda s: self._failure_counts.get(s, 0))
        
        return candidates[:self.max_retries]
    
    def record_failure(self, store: str) -> None:
        """Record a failure for a store"""
        self._failure_counts[store] += 1
        self._last_failure[store] = time.time()
    
    def record_success(self, store: str) -> None:
        """Record success, reduce failure count"""
        if store in self._failure_counts:
            self._failure_counts[store] = max(0, self._failure_counts[store] - 1)
    
    def should_fallback(self, store: str, error_type: str) -> bool:
        """
        Determine if we should try fallback store.
        
        Args:
            store: Store that failed
            error_type: Type of failure
        
        Returns:
            True if fallback should be attempted
        """
        retryable_errors = [
            "timeout", "rate_limit", "throttled", "try_again",
            "cart_failed", "checkout_failed", "session_expired",
            "connection", "503", "502", "429",
        ]
        
        error_lower = error_type.lower()
        return any(err in error_lower for err in retryable_errors)
    
    def reset_counts(self) -> None:
        """Reset all failure counts"""
        self._failure_counts.clear()
        self._last_failure.clear()


_bin_router = BINRouter()
_price_filter = PriceFilter()
_parallel_fallback = ParallelFallback()


def get_best_store_for_card(card_num: str, available_stores: List[str]) -> Optional[str]:
    """Get optimal store for a card based on BIN history"""
    return _bin_router.get_best_store(card_num, available_stores)


def record_bin_result(card_num: str, store: str, success: bool, reason: str = "") -> None:
    """Record result for BIN routing optimization"""
    _bin_router.record_result(card_num, store, success, reason)


def filter_stores_by_price(stores: List[Dict], min_price: float = 1.0, max_price: float = 100.0) -> List[Dict]:
    """Filter stores by price range"""
    return _price_filter.filter_stores(stores, min_price, max_price)


def get_fallback_stores(failed_store: str, all_stores: List[str]) -> List[str]:
    """Get fallback stores after primary failure"""
    return _parallel_fallback.get_fallback_stores(failed_store, all_stores)


def should_try_fallback(store: str, error: str) -> bool:
    """Check if fallback should be attempted"""
    return _parallel_fallback.should_fallback(store, error)


def record_store_failure(store: str) -> None:
    """Record store failure for fallback logic"""
    _parallel_fallback.record_failure(store)


def record_store_success(store: str) -> None:
    """Record store success"""
    _parallel_fallback.record_success(store)
