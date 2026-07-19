# -*- coding: utf-8 -*-
"""
Shared defaults for trading skills.

This module centralises:
1. The default active skill set used by agent entrypoints
2. The fallback skill subset used by the multi-agent router
3. Common prompt fragments that previously drifted across multiple files
4. Helper utilities for skill-specific agent naming
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional


_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "strategies"

SKILL_AGENT_PREFIX = "skill_"
LEGACY_STRATEGY_AGENT_PREFIX = "strategy_"
SKILL_CONSENSUS_AGENT_NAME = "skill_consensus"
LEGACY_STRATEGY_CONSENSUS_AGENT_NAME = "strategy_consensus"

CORE_TRADING_SKILL_POLICY_ZH = """## Mark Minervini 趨勢交易基線（必須嚴格遵守）

目前啟用的技能可補充分析視角；所有結論仍須以已驗證的市場、價格、成交量與財務資料為準。此基線採用 Mark Minervini 的趨勢模板／SEPA 思維：順勢、等待型態成熟、在風險明確時才出手。

### 1. 市場環境與趨勢模板
- 先判斷台股與美股所屬市場環境，再評估個股；市場趨勢不利時降低曝險，不因單一訊號強行買進。
- 長期資料足夠時，優先檢查 Stage 2／SEPA：價格位於中長期均線之上、均線趨勢向上、接近相對高檔而非長期低檔。
- 短期多頭排列以 MA5 > MA10 > MA20 為正向條件，但不單獨構成買進理由；均線向上發散優於糾結。

### 2. 進場：型態、樞紐與量能必須同時確認
- 優先等候 VCP／整理平台的樞紐（Pivot）帶量突破，或縮量回測 MA5／MA10 後重新轉強；只可引用資料中實際驗證的型態與量能。
- 現價偏離 MA5 超過 5% 時不得追價；乖離率低於 2% 才可能屬合理位置，2% 至 5% 僅能在其他條件完整時列為條件式小部位方案。
- 未確認突破、量能不足、風險報酬比低於 2，或關鍵資料缺失時，動作只能為觀察／持有／避開，不得把分數直接轉成買進。

### 3. 風險與部位管理
- 每一項建議都要寫出觸發條件、失效條件與停損依據；初始風險以結構停損為主，通常不宜超過進場價約 5% 至 8%，但不可虛構價格。
- 禁止向下攤平；若突破失敗、跌破關鍵支撐或停損，應依事先定義的失效條件減碼或退出。
- 先以小部位驗證，再隨趨勢與獲利保護逐步加碼；不得預設保證報酬或必然上漲。

### 4. 新上市 ETF 與資料完整性
- 歷史未滿 252 根日線的新上市 ETF，仍要利用已取得的 MA5／MA10／MA20、量價、MACD、RSI 與短期高低點做短期分析；Stage 2、SEPA、VCP、長期 Pivot 必須標示「未取得／暫停判定」，不可因上市時間短而給 0 分、賣出或看空。
- 若日線、成交量、即時價格、法人、財報或新聞任何一項未取得，必須清楚標示來源與狀態；不得補造資料、目標價、公司名稱、法人結論或買賣點。
"""

TECHNICAL_SKILL_RULES_EN = """## Default Skill Baseline

Treat the currently activated skills as the primary analysis lens, but keep the
following default risk controls as the shared baseline:

- Bullish alignment: MA5 > MA10 > MA20
- Bias from MA5 < 2% -> ideal buy zone; 2-5% -> small position; > 5% -> no chase
- Shrink-pullback to MA5 is the preferred entry rhythm
- Below MA20 -> hold off unless the active skill explicitly proves a better setup
"""


def get_default_trading_skill_policy(*, explicit_skill_selection: bool) -> str:
    """Return the legacy default trading baseline only for implicit/default runs.

    When a caller explicitly chooses a skill (via request payload or config),
    analysis should follow that selected skill alone instead of silently
    layering the old bull-trend baseline on top.
    """
    if explicit_skill_selection:
        return ""
    return CORE_TRADING_SKILL_POLICY_ZH


def get_default_technical_skill_policy(*, explicit_skill_selection: bool) -> str:
    """Return the technical-agent baseline only for implicit/default runs."""
    if explicit_skill_selection:
        return ""
    return TECHNICAL_SKILL_RULES_EN


@lru_cache(maxsize=1)
def _load_builtin_skill_catalog() -> tuple[object, ...]:
    try:
        from src.agent.skills.base import load_skills_from_directory

        return tuple(load_skills_from_directory(_BUILTIN_SKILLS_DIR))
    except Exception:
        return ()


def _coerce_priority(value: object, default: int = 100) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_available_ids(available_skill_ids: Optional[Iterable[str]]) -> List[str]:
    normalized: List[str] = []
    if available_skill_ids is None:
        return normalized
    for skill_id in available_skill_ids:
        if isinstance(skill_id, str):
            cleaned = skill_id.strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
    return normalized


def _normalize_skill_inputs(
    skills: Optional[Iterable[object]],
    available_skill_ids: Optional[Iterable[str]] = None,
) -> tuple[List[object], List[str]]:
    normalized_available = _normalize_available_ids(available_skill_ids)

    if skills is None:
        return list(_load_builtin_skill_catalog()), normalized_available

    skill_pool: List[object] = []
    for item in skills:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned and cleaned not in normalized_available:
                normalized_available.append(cleaned)
            continue
        if item is not None:
            skill_pool.append(item)
    return skill_pool, normalized_available


def _sort_skill_pool(skills: Iterable[object]) -> List[object]:
    return sorted(
        skills,
        key=lambda skill: (
            _coerce_priority(getattr(skill, "default_priority", 100)),
            str(getattr(skill, "display_name", "") or getattr(skill, "name", "")),
            str(getattr(skill, "name", "")),
        ),
    )


def _iter_candidate_skills(
    skills: Optional[Iterable[object]],
    *,
    available_skill_ids: Optional[Iterable[str]] = None,
    user_invocable_only: bool = True,
) -> tuple[List[object], List[str]]:
    skill_pool, normalized_available = _normalize_skill_inputs(skills, available_skill_ids)
    available_lookup = set(normalized_available)

    candidates: List[object] = []
    for skill in _sort_skill_pool(skill_pool):
        skill_id = str(getattr(skill, "name", "")).strip()
        if not skill_id:
            continue
        if user_invocable_only and not bool(getattr(skill, "user_invocable", True)):
            continue
        if available_lookup and skill_id not in available_lookup:
            continue
        candidates.append(skill)

    return candidates, normalized_available


def _slice_skill_ids(skill_ids: List[str], max_count: Optional[int]) -> List[str]:
    if max_count is None:
        return skill_ids
    return skill_ids[:max_count]


def _pick_primary_default_skill_id(candidates: List[object]) -> str:
    preferred = [
        str(getattr(skill, "name", "")).strip()
        for skill in candidates
        if bool(getattr(skill, "default_active", False))
    ]
    if preferred:
        return preferred[0]

    fallback = [str(getattr(skill, "name", "")).strip() for skill in candidates]
    if fallback:
        return fallback[0]

    return ""


def get_default_active_skill_ids(
    skills: Optional[Iterable[object]] = None,
    max_count: Optional[int] = None,
    available_skill_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    candidates, normalized_available = _iter_candidate_skills(
        skills,
        available_skill_ids=available_skill_ids,
    )
    default_skill_id = _pick_primary_default_skill_id(candidates)
    if default_skill_id:
        return _slice_skill_ids([default_skill_id], max_count)

    return _slice_skill_ids(normalized_available[:1], max_count)


def get_default_router_skill_ids(
    skills: Optional[Iterable[object]] = None,
    max_count: Optional[int] = None,
    available_skill_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    candidates, normalized_available = _iter_candidate_skills(
        skills,
        available_skill_ids=available_skill_ids,
    )
    preferred = [
        str(getattr(skill, "name", "")).strip()
        for skill in candidates
        if bool(getattr(skill, "default_router", False))
    ]
    if preferred:
        return _slice_skill_ids(preferred, max_count)

    return get_default_active_skill_ids(
        candidates,
        max_count=max_count,
        available_skill_ids=normalized_available,
    )


def get_regime_skill_ids(
    regime: str,
    skills: Optional[Iterable[object]] = None,
    max_count: Optional[int] = None,
    available_skill_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    candidates, normalized_available = _iter_candidate_skills(
        skills,
        available_skill_ids=available_skill_ids,
    )
    regime_name = (regime or "").strip().lower()
    if regime_name:
        matched = []
        for skill in candidates:
            market_regimes = getattr(skill, "market_regimes", None) or []
            normalized_regimes = {
                str(item).strip().lower()
                for item in market_regimes
                if str(item).strip()
            }
            if regime_name in normalized_regimes:
                matched.append(str(getattr(skill, "name", "")).strip())
        if matched:
            return _slice_skill_ids(matched, max_count)

    return get_default_router_skill_ids(
        candidates,
        max_count=max_count,
        available_skill_ids=normalized_available,
    )


def get_primary_default_skill_id(
    skills: Optional[Iterable[object]] = None,
    available_skill_ids: Optional[Iterable[str]] = None,
) -> str:
    defaults = get_default_active_skill_ids(skills, max_count=1, available_skill_ids=available_skill_ids)
    return defaults[0] if defaults else ""


def _build_regime_skill_ids(skills: Iterable[object]) -> Dict[str, List[str]]:
    regime_map: Dict[str, List[str]] = {}
    for skill in _sort_skill_pool(skills):
        skill_id = str(getattr(skill, "name", "")).strip()
        if not skill_id:
            continue
        for regime in getattr(skill, "market_regimes", None) or []:
            regime_name = str(regime).strip().lower()
            if not regime_name:
                continue
            regime_map.setdefault(regime_name, []).append(skill_id)
    return regime_map


DEFAULT_ACTIVE_SKILL_IDS: tuple[str, ...] = tuple(get_default_active_skill_ids())
DEFAULT_ROUTER_SKILL_IDS: tuple[str, ...] = tuple(get_default_router_skill_ids())
PRIMARY_DEFAULT_SKILL_ID = get_primary_default_skill_id()
REGIME_SKILL_IDS: Dict[str, List[str]] = _build_regime_skill_ids(_load_builtin_skill_catalog())


def build_skill_agent_name(skill_id: str) -> str:
    return f"{SKILL_AGENT_PREFIX}{skill_id}"


def extract_skill_id(agent_name: Optional[str]) -> Optional[str]:
    if not agent_name or not isinstance(agent_name, str):
        return None
    for prefix in (SKILL_AGENT_PREFIX, LEGACY_STRATEGY_AGENT_PREFIX):
        if agent_name.startswith(prefix):
            return agent_name[len(prefix):]
    return None


def is_skill_agent_name(agent_name: Optional[str]) -> bool:
    return extract_skill_id(agent_name) is not None


def is_skill_consensus_name(agent_name: Optional[str]) -> bool:
    return agent_name in {SKILL_CONSENSUS_AGENT_NAME, LEGACY_STRATEGY_CONSENSUS_AGENT_NAME}
