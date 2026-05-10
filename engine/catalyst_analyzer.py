"""
Integral Trading — Catalyst Analyzer
=======================================
Analisa qualitativamente o catalisador de cada candidato EP.
Usa web search em tempo real para descobrir o que causou o gap.

Para cada ticker:
1. Pesquisa notícias recentes via web search
2. Identifica o tipo de catalisador (dos 22 tipos EP do Pradeep)
3. Avalia a qualidade segundo os critérios EP
4. Retorna análise estruturada para o Decision Engine
"""

import json
import logging
import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"


@dataclass
class CatalystAnalysis:
    """Resultado da análise qualitativa do catalisador."""
    ticker:              str
    catalyst_type:       str        # tipo EP (dos 22 do Pradeep)
    catalyst_summary:    str        # descrição curta do catalisador
    catalyst_quality:    str        # HIGH / MEDIUM / LOW
    quality_score:       float      # 0-100
    is_neglected:        bool       # stock estava fora do radar?
    is_first_surprise:   bool       # primeiro grande earnings surprise?
    is_sustainable:      bool       # catalisador sustentável?
    already_priced_in:   bool       # surpresa já reflectida no preço?
    red_flags:           list       # alertas negativos
    green_flags:         list       # factores positivos
    reasoning:           str        # análise completa
    news_found:          bool       # foi possível encontrar notícias?
    created_at:          str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    @property
    def quality_icon(self) -> str:
        return {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(
            self.catalyst_quality, "⚪")

    def to_dict(self) -> dict:
        return {
            "ticker":           self.ticker,
            "catalyst_type":    self.catalyst_type,
            "catalyst_summary": self.catalyst_summary,
            "catalyst_quality": self.catalyst_quality,
            "quality_score":    round(self.quality_score, 1),
            "quality_icon":     self.quality_icon,
            "is_neglected":     self.is_neglected,
            "is_first_surprise": self.is_first_surprise,
            "is_sustainable":   self.is_sustainable,
            "already_priced_in": self.already_priced_in,
            "red_flags":        self.red_flags,
            "green_flags":      self.green_flags,
            "reasoning":        self.reasoning,
            "news_found":       self.news_found,
            "created_at":       self.created_at,
        }


# Os 22 tipos de catalisadores EP do Pradeep
EP_CATALYST_TYPES = [
    "Earnings Growth 100%+",
    "Earnings 40%+",
    "Earnings Beat Wide Margin",
    "Earnings Other",
    "Sales 100%+ (sem earnings)",
    "IPO Breakout",
    "Retail Momentum",
    "Top Sector",
    "New Order/Contract",
    "Buyout/Merger",
    "New Product Launch",
    "Regulatory Changes",
    "Drug Approval",
    "Drug/Marketing Tie-Up",
    "Natural Disaster/War/Disease",
    "Shortages",
    "Rate Increase",
    "Media Mention",
    "Analyst Upgrade/Downgrade",
    "Dividend Declaration",
    "Financial Engineering",
    "Junk Bottom Rally",
    "Outro",
]


class CatalystAnalyzer:
    """
    Analisa catalisadores EP com web search em tempo real.

    Uso:
        analyzer = CatalystAnalyzer()
        analysis = analyzer.analyze("HIMS", gap_pct=47.5, gap_date="2026-03-09")
        print(analysis.catalyst_type, analysis.catalyst_quality)
    """

    def analyze(
        self,
        ticker: str,
        gap_pct: float = 0,
        gap_date: str = "",
        current_price: float = 0,
    ) -> CatalystAnalysis:
        """
        Analisa o catalisador de um ticker.
        Pesquisa notícias e avalia segundo critérios EP do Pradeep.
        """
        if not ANTHROPIC_API_KEY:
            return self._fallback(ticker, "API não configurada")

        try:
            return self._analyze_with_search(ticker, gap_pct, gap_date, current_price)
        except Exception as e:
            logger.error("Erro ao analisar catalisador de " + ticker + ": " + str(e))
            return self._fallback(ticker, str(e))

    def analyze_batch(self, candidates: list) -> dict:
        """
        Analisa múltiplos candidatos.
        Retorna dicionário {ticker: CatalystAnalysis}.
        """
        results = {}
        for c in candidates:
            logger.info("A analisar catalisador: " + c.ticker)
            analysis = self.analyze(
                ticker=c.ticker,
                gap_pct=c.gap_pct,
                gap_date=getattr(c, "gap_date", ""),
                current_price=c.current_price,
            )
            results[c.ticker] = analysis
            logger.info(
                analysis.quality_icon + " " + c.ticker +
                " — " + analysis.catalyst_type +
                " | Qualidade: " + analysis.catalyst_quality +
                " (" + str(round(analysis.quality_score, 0)) + ")"
            )
        return results

    # ── Análise com web search ────────────────────────────────────────────────

    def _analyze_with_search(
        self,
        ticker: str,
        gap_pct: float,
        gap_date: str,
        current_price: float,
    ) -> CatalystAnalysis:
        """Chama a API com web search para analisar o catalisador."""

        catalyst_types_str = "\n".join(
            "- " + t for t in EP_CATALYST_TYPES
        )

        prompt = f"""És o especialista EP. Para o ticker {ticker}, que fez um gap de {gap_pct:.1f}% recentemente:

1. Pesquisa o que causou este gap (notícias recentes, earnings, eventos)
2. Avalia a qualidade do catalisador segundo o método EP do Pradeep Bonde

**Critérios de qualidade EP:**
- Neglect: o stock estava fora do radar antes do evento?
- Primeiro grande surprise: é a primeira grande aceleração?
- Sustentável: o catalisador representa uma mudança estrutural?
- Já priced in: a surpresa ainda não está reflectida no preço?

**Tipos de catalisadores EP (escolhe o mais adequado):**
{catalyst_types_str}

Responde APENAS em JSON válido:
{{
  "catalyst_type": "tipo do catalisador (da lista acima)",
  "catalyst_summary": "descrição em 1 frase do que aconteceu",
  "catalyst_quality": "HIGH" ou "MEDIUM" ou "LOW",
  "quality_score": número de 0 a 100,
  "is_neglected": true ou false,
  "is_first_surprise": true ou false,
  "is_sustainable": true ou false,
  "already_priced_in": true ou false,
  "red_flags": ["lista de alertas negativos"],
  "green_flags": ["lista de factores positivos"],
  "reasoning": "análise em 3-4 frases em português",
  "news_found": true ou false
}}"""

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model":      CLAUDE_MODEL,
                "max_tokens": 800,
                "tools": [
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                    }
                ],
                "system": "És um especialista EP rigoroso. Pesquisas notícias reais e respondes APENAS em JSON válido.",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Extrair o JSON da resposta
        # A API pode retornar server_tool_use + web_search_tool_result + text
        text_content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_content += block.get("text", "")

        # Limpar e fazer parse do JSON
        text_content = text_content.strip()
        if "```" in text_content:
            parts = text_content.split("```")
            for part in parts:
                if "{" in part:
                    text_content = part.replace("json", "").strip()
                    break

        # Encontrar o JSON no texto
        start = text_content.find("{")
        end   = text_content.rfind("}") + 1
        if start >= 0 and end > start:
            text_content = text_content[start:end]

        result = json.loads(text_content)

        return CatalystAnalysis(
            ticker=ticker,
            catalyst_type=result.get("catalyst_type", "Outro"),
            catalyst_summary=result.get("catalyst_summary", ""),
            catalyst_quality=result.get("catalyst_quality", "MEDIUM"),
            quality_score=float(result.get("quality_score", 50)),
            is_neglected=bool(result.get("is_neglected", False)),
            is_first_surprise=bool(result.get("is_first_surprise", False)),
            is_sustainable=bool(result.get("is_sustainable", False)),
            already_priced_in=bool(result.get("already_priced_in", False)),
            red_flags=result.get("red_flags", []),
            green_flags=result.get("green_flags", []),
            reasoning=result.get("reasoning", ""),
            news_found=bool(result.get("news_found", False)),
        )

    def _fallback(self, ticker: str, reason: str) -> CatalystAnalysis:
        """Análise vazia quando API não está disponível."""
        return CatalystAnalysis(
            ticker=ticker,
            catalyst_type="Outro",
            catalyst_summary="Análise indisponível: " + reason,
            catalyst_quality="MEDIUM",
            quality_score=50.0,
            is_neglected=False,
            is_first_surprise=False,
            is_sustainable=False,
            already_priced_in=False,
            red_flags=["Análise qualitativa indisponível"],
            green_flags=[],
            reasoning="Não foi possível analisar o catalisador.",
            news_found=False,
        )
