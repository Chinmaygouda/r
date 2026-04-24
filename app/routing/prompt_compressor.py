"""
Adaptive Prompt Compressor — Self-Learning Version
====================================================
Combines:
  1. Heuristic compression (rule-based, zero cost, <1ms)
  2. TF-IDF selective sentence scoring (sklearn, lightweight)
  3. Adaptive pattern learning via feedback loop
     - Tracks which compression patterns produce good AI responses
     - Learns new stop-phrases and filler patterns over time
     - Persists learned patterns to disk (JSON)

Runs 100% locally. Improves with every request.
No internet required. No GPU required.
"""

import re
import os
import json
import time
from typing import Tuple, List
from difflib import SequenceMatcher
from collections import defaultdict


# ─────────────────────────────────────────────────────────────
#  PERSISTENCE: Where learned patterns are saved to disk
# ─────────────────────────────────────────────────────────────
LEARNED_PATTERNS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "learned_compression_patterns.json"
)


class AdaptivePromptCompressor:
    """
    Self-learning prompt compressor.

    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │  INPUT PROMPT                                               │
    │       ↓                                                     │
    │  [1] Heuristic Pipeline (comment strip, filler remove...)  │
    │       ↓                                                     │
    │  [2] TF-IDF Sentence Scoring (drop low-info sentences)     │
    │       ↓                                                     │
    │  [3] Adaptive Pattern Filter (learned stop-phrases)        │
    │       ↓                                                     │
    │  COMPRESSED PROMPT                                          │
    │       ↓                                                     │
    │  [4] Feedback Loop → learn new patterns if response=good   │
    └─────────────────────────────────────────────────────────────┘
    """

    # ── Static filler words ──
    STATIC_FILLER_WORDS = [
        r'\bum\b', r'\buh\b', r'\bhmm\b', r'\bhey\b', r'\bhi\b', r'\bhello\b',
        r'\bbasically\b', r'\bactually\b', r'\bliterally\b', r'\bobviously\b',
        r'\breally\b', r'\bkind of\b', r'\bsort of\b', r'\bjust\b',
        r'\bI think maybe\b', r'\bI mean\b', r'\byou know\b', r'\bhonestly\b',
    ]

    # ── Static politeness map ──
    # Aggressively strip conversational fluff from short prompts
    STATIC_POLITENESS_MAP = [
        # Extreme politeness
        (r'Could you please kindly', 'Please'),
        (r'Would you be so kind as to', 'Please'),
        (r'I was wondering if you could', 'Please'),
        (r'I would really appreciate it if you could', 'Please'),
        (r'Thank you so much[!.]*\s*$', ''),
        (r'Thank you[!.]*\s*$', ''),
        (r'I appreciate your (help|assistance)\.?', ''),
        # Conversational Intro Fluff
        (r'^(hey|hi|hello|greetings)[!.,\s]+', ''),
        (r'can you (please )?(tell|explain to|guide|show) me\b', 'explain'),
        (r'how can (you|u|i|we) be like\b', ''),
        (r'(what is|wts|whats) the use of\b', 'why use'),
        (r'that thing which is\b', ''),
        (r'I (just )?want to know\b', ''),
        (r'as if I\'m a complete beginner', 'simply'),
    ]

    def __init__(self):
        # Load learned patterns from disk
        self.learned_patterns = self._load_learned_patterns()
        # Track per-session compression stats for feedback
        self._session_log = {}  # {session_id: {pattern: used_count}}

        # Try to load TF-IDF (lightweight sklearn)
        self._tfidf_available = False
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            import numpy as np
            self._tfidf_available = True
        except ImportError:
            pass

    # ═══════════════════════════════════════════════════════
    #  MAIN COMPRESS METHOD
    # ═══════════════════════════════════════════════════════
    def compress(self, prompt: str, category: str = "UTILITY",
                 session_id: str = None) -> Tuple[str, dict]:
        """
        Compress prompt with adaptive learning.

        Args:
            prompt: Raw input prompt
            category: CODE / CHAT / ANALYSIS / etc.
            session_id: Optional ID to track compression for feedback

        Returns:
            (compressed_prompt, metrics_dict)
        """
        original_words = len(prompt.split())
        start_time = time.time()

        # Step 1: Heuristic pipeline
        text = self._heuristic_pipeline(prompt, category)

        # Step 2: TF-IDF sentence scoring (for long prompts)
        if self._tfidf_available and original_words > 80:
            text = self._tfidf_filter(text, category, keep_ratio=0.85)

        # Step 3: Apply learned adaptive patterns
        text, patterns_used = self._apply_learned_patterns(text, category)

        # Step 4: Cleanup
        text = self._final_cleanup(text)

        # Track for feedback if session_id given
        if session_id:
            self._session_log[session_id] = {
                "original": prompt,
                "compressed": text,
                "patterns_used": patterns_used,
                "category": category
            }

        compressed_words = len(text.split())
        ms_taken = round((time.time() - start_time) * 1000, 2)
        savings_pct = round((1 - compressed_words / max(original_words, 1)) * 100, 1)

        return text, {
            "original_words": original_words,
            "compressed_words": compressed_words,
            "savings_percent": max(savings_pct, 0.0),
            "latency_ms": ms_taken,
            "patterns_used": patterns_used,
            "tfidf_used": self._tfidf_available and original_words > 80
        }

    # ═══════════════════════════════════════════════════════
    #  FEEDBACK LOOP — SELF LEARNING CORE
    # ═══════════════════════════════════════════════════════
    def learn_from_feedback(self, session_id: str, reward: float):
        """
        Called after AI responds. If reward is good (≥0.7),
        the patterns used in this session are reinforced.
        If reward is poor (<0.3), patterns are penalized.

        This is how the compressor self-improves over time.

        Args:
            session_id: Same ID passed to compress()
            reward: Score 0-1 (from Thompson Sampler reward system)
        """
        if session_id not in self._session_log:
            return

        log = self._session_log[session_id]
        category = log["category"]
        patterns_used = log["patterns_used"]

        for pattern in patterns_used:
            key = f"{category}::{pattern}"

            if key not in self.learned_patterns["pattern_scores"]:
                self.learned_patterns["pattern_scores"][key] = {
                    "uses": 0, "total_reward": 0.0, "avg_reward": 0.0
                }

            entry = self.learned_patterns["pattern_scores"][key]
            entry["uses"] += 1
            entry["total_reward"] += reward
            entry["avg_reward"] = entry["total_reward"] / entry["uses"]

        # If compressed response was very bad, record as unsafe
        if reward < 0.2:
            original = log["original"]
            for pattern in patterns_used:
                if pattern not in self.learned_patterns["penalized_patterns"]:
                    self.learned_patterns["penalized_patterns"].append(pattern)
                    print(f"[COMPRESSOR] Penalized pattern: '{pattern}' (reward={reward:.2f})")

        # Extract new learned stop-phrases from good responses
        if reward >= 0.8:
            self._extract_new_filler_patterns(log["original"], log["compressed"], category)

        # Persist to disk
        self._save_learned_patterns()
        del self._session_log[session_id]

    # ═══════════════════════════════════════════════════════
    #  HEURISTIC PIPELINE
    # ═══════════════════════════════════════════════════════
    def _heuristic_pipeline(self, prompt: str, category: str) -> str:
        """Apply rule-based compression."""
        text = self._normalize_whitespace(prompt)

        if category.upper() == "CODE":
            text = self._compress_code(text)
        else:
            text = self._compress_general(text)

        text = self._deduplicate_sentences(text)
        return text

    def _compress_code(self, prompt: str) -> str:
        lines = prompt.split('\n')
        result = []
        prev_normalized = None
        repeat_count = 0
        blank_streak = 0

        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                blank_streak += 1
                if blank_streak == 1:
                    result.append('')
                continue
            else:
                blank_streak = 0

            lstripped = stripped.lstrip()
            if lstripped.startswith('#'):
                important = any(kw in lstripped.upper() for kw in
                                ['TODO', 'FIXME', 'BUG', 'HACK', 'NOTE', 'WARNING'])
                if not important:
                    continue

            code_line = re.sub(r'\s+#(?!\s*type:)\s+[^\'\"]+$', '', stripped)
            normalized = re.sub(r'\d+', 'N', re.sub(r'["\'].*?["\']', 'S', code_line))

            if normalized == prev_normalized and normalized.strip():
                repeat_count += 1
                if repeat_count <= 2:
                    result.append(code_line)
                elif repeat_count == 3:
                    result.append(f"    # ... ({repeat_count}+ similar lines)")
            else:
                prev_normalized = normalized
                repeat_count = 1
                result.append(code_line)

        return '\n'.join(result)

    def _compress_general(self, text: str) -> str:
        for pattern, replacement in self.STATIC_POLITENESS_MAP:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        for filler in self.STATIC_FILLER_WORDS:
            text = re.sub(filler, '', text, flags=re.IGNORECASE)
        text = self._fix_artifacts(text)
        return text

    def _deduplicate_sentences(self, text: str) -> str:
        lines = text.split('\n')
        unique, seen = [], []
        for line in lines:
            s = line.strip()
            if not s:
                unique.append(line)
                continue
            is_dup = any(SequenceMatcher(None, s.lower(), p.lower()).ratio() > 0.85 for p in seen)
            if not is_dup:
                unique.append(line)
                seen.append(s)
        return '\n'.join(unique)

    # ═══════════════════════════════════════════════════════
    #  TF-IDF SENTENCE SCORING (for long prompts)
    # ═══════════════════════════════════════════════════════
    def _tfidf_filter(self, text: str, category: str, keep_ratio: float = 0.85) -> str:
        """
        Score each sentence by information density using TF-IDF.
        Drop the lowest-scoring sentences to hit keep_ratio.
        CODE prompts: keep all (don't drop code lines).
        """
        if category.upper() == "CODE":
            return text  # Never drop code lines

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            import numpy as np

            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
            if len(sentences) <= 3:
                return text  # Too short to filter

            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf_matrix = vectorizer.fit_transform(sentences)
            scores = tfidf_matrix.sum(axis=1).A1  # Sum of TF-IDF weights per sentence

            # Keep top keep_ratio% sentences by score
            threshold = np.percentile(scores, (1 - keep_ratio) * 100)
            kept = [s for s, score in zip(sentences, scores) if score >= threshold]

            return ' '.join(kept)
        except Exception:
            return text  # Fail silently

    # ═══════════════════════════════════════════════════════
    #  ADAPTIVE PATTERN APPLICATION
    # ═══════════════════════════════════════════════════════
    def _apply_learned_patterns(self, text: str, category: str) -> Tuple[str, List[str]]:
        """Apply patterns learned from past feedback. Skip penalized ones."""
        used = []
        for pattern in self.learned_patterns.get("learned_fillers", []):
            if pattern in self.learned_patterns.get("penalized_patterns", []):
                continue  # Skip patterns that hurt quality
            try:
                new_text = re.sub(r'\b' + re.escape(pattern) + r'\b', '', text, flags=re.IGNORECASE)
                if new_text != text:
                    text = new_text
                    used.append(pattern)
            except re.error:
                pass
        return self._fix_artifacts(text), used

    # ═══════════════════════════════════════════════════════
    #  SELF-LEARNING: Extract new filler patterns
    # ═══════════════════════════════════════════════════════
    def _extract_new_filler_patterns(self, original: str, compressed: str, category: str):
        """
        Compare original vs compressed to find new removable phrases.
        If a phrase was removed AND the response was good, add it to learned_fillers.
        """
        # Find words in original not in compressed (rough heuristic)
        orig_words = set(original.lower().split())
        comp_words = set(compressed.lower().split())
        removed_words = orig_words - comp_words

        # Filter: only add single short words (not code tokens)
        new_fillers = [
            w for w in removed_words
            if len(w) > 2 and len(w) < 15
            and w.isalpha()
            and w not in self.learned_patterns.get("learned_fillers", [])
            and w not in ["the", "and", "for", "are", "was", "can", "not", "you", "this"]
        ]

        if new_fillers:
            self.learned_patterns.setdefault("learned_fillers", [])
            self.learned_patterns["learned_fillers"].extend(new_fillers[:3])  # max 3 new per call
            print(f"[COMPRESSOR] Learned {len(new_fillers)} new filler patterns: {new_fillers[:3]}")

    # ═══════════════════════════════════════════════════════
    #  PERSISTENCE
    # ═══════════════════════════════════════════════════════
    def _load_learned_patterns(self) -> dict:
        os.makedirs(os.path.dirname(LEARNED_PATTERNS_PATH), exist_ok=True)
        if os.path.exists(LEARNED_PATTERNS_PATH):
            try:
                with open(LEARNED_PATTERNS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"[COMPRESSOR] Loaded {len(data.get('learned_fillers', []))} learned patterns from disk")
                    return data
            except Exception:
                pass
        return {
            "learned_fillers": [],
            "penalized_patterns": [],
            "pattern_scores": {}
        }

    def _save_learned_patterns(self):
        try:
            os.makedirs(os.path.dirname(LEARNED_PATTERNS_PATH), exist_ok=True)
            with open(LEARNED_PATTERNS_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.learned_patterns, f, indent=2)
        except Exception as e:
            print(f"[COMPRESSOR] Could not save patterns: {e}")

    # ═══════════════════════════════════════════════════════
    #  UTILITIES
    # ═══════════════════════════════════════════════════════
    def _normalize_whitespace(self, text: str) -> str:
        text = text.replace('\t', '    ')
        text = re.sub(r'[ \t]+\n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'([!?.]){2,}', r'\1', text)
        return text

    def _fix_artifacts(self, text: str) -> str:
        text = re.sub(r'(,\s*){2,}', ', ', text)
        text = re.sub(r'^\s*,\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s+([.,?!;:])', r'\1', text)
        text = re.sub(r'  +', ' ', text)
        text = re.sub(r'^\s*[,;]\s*', '', text, flags=re.MULTILINE)
        return text

    def _final_cleanup(self, text: str) -> str:
        lines = [line.rstrip() for line in text.split('\n')]
        text = '\n'.join(lines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def get_stats(self) -> dict:
        """Return stats on learned patterns for monitoring."""
        return {
            "learned_fillers": len(self.learned_patterns.get("learned_fillers", [])),
            "penalized_patterns": len(self.learned_patterns.get("penalized_patterns", [])),
            "pattern_scores": len(self.learned_patterns.get("pattern_scores", {})),
            "tfidf_available": self._tfidf_available
        }


# ─────────────────────────────────────────────────
#  Global singleton
# ─────────────────────────────────────────────────
_compressor = None

def get_prompt_compressor() -> AdaptivePromptCompressor:
    """Get or create global adaptive prompt compressor instance."""
    global _compressor
    if _compressor is None:
        _compressor = AdaptivePromptCompressor()
    return _compressor
