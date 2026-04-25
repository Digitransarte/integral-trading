"""
Integral Trading — Especialista Episodic Pivot
================================================
Especialista com conhecimento carregado dinamicamente do ficheiro
knowledge/ep_strategy.json — editável sem tocar em código.
"""

import json
import os
from engine.specialist import BaseSpecialist


def _load_knowledge() -> dict:
    """Carrega o ficheiro de conhecimento EP."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base_dir, "knowledge", "ep_strategy.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _build_system_prompt(k: dict) -> str:
    """Constrói o system prompt a partir do knowledge JSON."""

    philosophy = k.get("philosophy", {})
    green_flags = k.get("green_flags", [])
    red_flags = k.get("red_flags", [])
    catalyst_types = k.get("catalyst_types", {})
    entry_rules = k.get("entry_rules", {})
    exit_rules = k.get("exit_rules", {})
    neglect = k.get("neglect_criteria", {})
    lessons = k.get("lessons_learned", [])
    knowledge_base = k.get("knowledge_base", [])

    green_str = "\n".join(f"  ✅ {f}" for f in green_flags)
    red_str   = "\n".join(f"  ❌ {f}" for f in red_flags)

    tier1 = "\n".join(f"  • {c}" for c in catalyst_types.get("tier_1_forte", []))
    tier3 = "\n".join(f"  • {c}" for c in catalyst_types.get("tier_3_fraco", []))

    lessons_str = ""
    if lessons:
        lessons_str = "\n## Lições aprendidas dos nossos trades\n"
        for l in lessons[-10:]:  # últimas 10
            lessons_str += f"  • [{l.get('trade','')}] {l.get('lesson','')} ({l.get('date','')})\n"

    kb_str = ""
    if knowledge_base:
        kb_str = "\n## Base de conhecimento (fontes primárias)\n"
        for kb in knowledge_base:
            kb_str += f"  • [{kb.get('source','')}] {kb.get('insight','')}\n"

    return f"""És o especialista em Episodic Pivots (EP) do sistema Integral Trading.

## A tua identidade

O teu conhecimento vem directamente das fontes primárias do Pradeep Bonde (Stockbee) — o criador do método EP — complementado pela experiência real dos backtests e forward tests feitos neste sistema.

Tens dois modos de operação que combinas naturalmente:

**Modo Professor:** Explicas o método EP em profundidade. Usas as fontes primárias como referência. Ajudas a desenvolver o entendimento da estratégia.

**Modo Analista:** Quando vês resultados de backtests ou trades reais, analisas com rigor o que está a funcionar e o que não está. Avalias candidatos EP usando os critérios abaixo.

## Filosofia central

{philosophy.get('summary', '')}

**Insight core:** {philosophy.get('core_insight', '')}

**Tipos de EP:**
- Growth EP: {philosophy.get('two_types', {}).get('growth_ep', '')}
- Turnaround EP: {philosophy.get('two_types', {}).get('turnaround_ep', '')}
- Young EP: {philosophy.get('young_eps', '')}

## Neglect — conceito central

{neglect.get('description', '')}

Sinais mensuráveis:
- Sem rally nos últimos {neglect.get('measurable_signals', {}).get('sem_rally_dias', 65)} dias
- Menos de {neglect.get('measurable_signals', {}).get('fundos_max', 30)} fundos em carteira
- Float ideal < {neglect.get('measurable_signals', {}).get('float_max_ideal', 25000000):,} acções
- Volume baixo por período prolongado

## Green flags (sinal de EP de qualidade)
{green_str}

## Red flags (eliminar o candidato)
{red_str}

## Catalisadores — Tier 1 (fortes, prioridade máxima)
{tier1}

## Catalisadores — Tier 3 (fracos, evitar)
{tier3}

## Regras de entrada
- Timing: {entry_rules.get('timing', '')}
- Stop loss: {exit_rules.get('stop_loss', {}).get('rule', '')}
- Take profit: {exit_rules.get('take_profit', {}).get('method', '')}

{kb_str}
{lessons_str}

## Tom e estilo
- Directo e prático — foco em acção e implementação
- Quando avalias um candidato, lista explicitamente os green flags e red flags presentes
- Quando não tens certeza, diz-o claramente
- Responde em português europeu
- Sê honesto sobre o que falhou nos trades reais
"""


class EPSpecialist(BaseSpecialist):

    name          = "Episodic Pivot"
    strategy_name = "ep"

    def __init__(self, *args, **kwargs):
        # Carregar knowledge do JSON
        self._knowledge_data = _load_knowledge()
        # Construir system prompt dinâmico
        self.system_prompt = _build_system_prompt(self._knowledge_data)
        super().__init__(*args, **kwargs)

    @property
    def knowledge(self) -> dict:
        """Acesso directo ao knowledge JSON para uso interno."""
        return self._knowledge_data

    def evaluate_candidate(self, ticker: str, data: dict) -> dict:
        """
        Avalia um candidato EP contra os critérios do knowledge JSON.
        Retorna score qualitativo + lista de green/red flags presentes.
        """
        green_flags_found = []
        red_flags_found   = []
        score_bonus       = 0

        float_shares = data.get("float_shares", None)
        volume_ratio = data.get("volume_ratio", 0)
        gap_pct      = data.get("gap_pct", 0)
        catalyst     = data.get("catalyst", "").lower()
        days_since   = data.get("days_since_gap", 0)
        fund_count   = data.get("fund_count", None)

        # Avaliar float
        if float_shares is not None:
            if float_shares < 10_000_000:
                green_flags_found.append("Float < 10M — movimento explosivo possível")
                score_bonus += 20
            elif float_shares < 25_000_000:
                green_flags_found.append("Float < 25M — ideal")
                score_bonus += 15
            elif float_shares > 100_000_000:
                red_flags_found.append("Float > 100M — tendência para pullbacks")
                score_bonus -= 15

        # Avaliar volume
        if volume_ratio >= 10:
            green_flags_found.append(f"Volume {volume_ratio:.1f}x — sinal de movimento grande")
            score_bonus += 20
        elif volume_ratio >= 5:
            green_flags_found.append(f"Volume {volume_ratio:.1f}x — bom")
            score_bonus += 10
        elif volume_ratio < 3:
            red_flags_found.append(f"Volume apenas {volume_ratio:.1f}x — abaixo do mínimo Pradeep (3x)")
            score_bonus -= 10

        # Avaliar janela de entrada
        if days_since <= 1:
            green_flags_found.append("Janela PRIME — entrada ideal")
            score_bonus += 10
        elif days_since > 10:
            red_flags_found.append(f"EP há {days_since} dias — fora da janela de entrada")
            score_bonus -= 20

        # Avaliar catalisador (simples, sem web search)
        tier1_keywords = ["earnings", "drug approval", "buyout", "merger", "contract", "ipo"]
        tier3_keywords = ["dividend", "media", "analyst upgrade", "downgrade", "junk"]
        if any(k in catalyst for k in tier1_keywords):
            green_flags_found.append("Catalisador Tier 1 detectado")
            score_bonus += 15
        elif any(k in catalyst for k in tier3_keywords):
            red_flags_found.append("Catalisador Tier 3 — fraco")
            score_bonus -= 15

        # Avaliar fundos
        if fund_count is not None and fund_count < 30:
            green_flags_found.append(f"Apenas {fund_count} fundos em carteira — neglect confirmado")
            score_bonus += 10

        return {
            "ticker":            ticker,
            "green_flags":       green_flags_found,
            "red_flags":         red_flags_found,
            "score_adjustment":  score_bonus,
            "recommendation":    "STRONG" if score_bonus >= 30 else "VALID" if score_bonus >= 0 else "WEAK",
        }