"""
Integral Trading — Tuning Agent
================================
Agente de afinação da estratégia EP com acesso a ferramentas reais:
  - read_file: lê qualquer ficheiro do projecto
  - write_file: edita estratégia, knowledge JSON, etc.
  - run_backtest: executa backtester e devolve métricas
  - update_knowledge: actualiza o knowledge JSON com lições aprendidas

Arquitectura agentic: loop de tool use até resposta final.
"""

import json
import os
import sys
import importlib
import subprocess
from datetime import datetime
from pathlib import Path
import requests
import logging

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

CLAUDE_MODEL_SMART  = "claude-sonnet-4-20250514"   # respostas complexas
CLAUDE_MODEL_FAST   = "claude-haiku-4-5-20251001"  # tool use e análise
MAX_TOKENS          = 2000
BASE_DIR     = Path(__file__).parent.parent


# ── Definição das ferramentas ─────────────────────────────────────────────────

TOOLS = [
    {
        "name": "read_file",
        "description": "Lê o conteúdo de um ficheiro do projecto Integral Trading. Usa para inspecionar a estratégia EP, backtester, knowledge JSON, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho relativo à raiz do projecto. Ex: 'engine/strategies/ep_strategy.py', 'knowledge/ep_strategy.json'"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Escreve ou substitui o conteúdo de um ficheiro do projecto. Usa para editar parâmetros da estratégia EP ou actualizar o knowledge JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho relativo à raiz do projecto."
                },
                "content": {
                    "type": "string",
                    "description": "Conteúdo completo a escrever no ficheiro."
                },
                "description": {
                    "type": "string",
                    "description": "Descrição breve da alteração feita."
                }
            },
            "required": ["path", "content", "description"]
        }
    },
    {
        "name": "run_backtest",
        "description": "Executa um backtest da estratégia EP e devolve as métricas completas incluindo breakdown por dimensão.",
        "input_schema": {
            "type": "object",
            "properties": {
                "universe": {
                    "type": "string",
                    "description": "Nome do universo ou lista de tickers separados por vírgula. Ex: 'principal' ou 'NVTS,HIMS,IONQ,AAPL'"
                },
                "start_date": {
                    "type": "string",
                    "description": "Data de início no formato YYYY-MM-DD. Default: 1 ano atrás."
                },
                "end_date": {
                    "type": "string",
                    "description": "Data de fim no formato YYYY-MM-DD. Default: hoje."
                },
                "entry_mode": {
                    "type": "string",
                    "description": "Modo de entrada: 'ep_close', 'next_day_open', ou 'next_day_filtered'. Default: 'ep_close'.",
                    "enum": ["ep_close", "next_day_open", "next_day_filtered"]
                }
            },
            "required": []
        }
    },
    {
        "name": "update_knowledge",
        "description": "Adiciona uma lição aprendida ao knowledge JSON da estratégia EP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lesson": {
                    "type": "string",
                    "description": "Descrição clara da lição aprendida."
                },
                "source": {
                    "type": "string",
                    "description": "Fonte da lição (ex: 'Backtest 38 trades — ep_close mode')"
                },
                "impact": {
                    "type": "string",
                    "description": "Impacto ou alteração feita com base nesta lição."
                }
            },
            "required": ["lesson", "source", "impact"]
        }
    }
]


# ── Execução das ferramentas ──────────────────────────────────────────────────

def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """Executa uma ferramenta e devolve o resultado como string."""

    if tool_name == "read_file":
        return _tool_read_file(tool_input["path"])

    elif tool_name == "write_file":
        return _tool_write_file(
            tool_input["path"],
            tool_input["content"],
            tool_input.get("description", "")
        )

    elif tool_name == "run_backtest":
        return _tool_run_backtest(
            universe=tool_input.get("universe", "principal"),
            start_date=tool_input.get("start_date", ""),
            end_date=tool_input.get("end_date", ""),
            entry_mode=tool_input.get("entry_mode", "ep_close"),
        )

    elif tool_name == "update_knowledge":
        return _tool_update_knowledge(
            lesson=tool_input["lesson"],
            source=tool_input["source"],
            impact=tool_input["impact"],
        )

    return f"Ferramenta '{tool_name}' não reconhecida."


def _tool_read_file(path: str) -> str:
    full_path = BASE_DIR / path
    if not full_path.exists():
        return f"Ficheiro não encontrado: {path}"
    try:
        content = full_path.read_text(encoding="utf-8")
        # Limitar a 8000 chars para não exceder o contexto
        if len(content) > 8000:
            content = content[:8000] + "\n\n[... truncado — ficheiro tem " + str(len(content)) + " chars]"
        return content
    except Exception as e:
        return f"Erro ao ler {path}: {str(e)}"


def _tool_write_file(path: str, content: str, description: str) -> str:
    # Segurança: só permite escrever em paths conhecidos
    allowed_prefixes = [
        "engine/strategies/",
        "engine/backtester.py",
        "knowledge/",
        "universes.py",
    ]
    if not any(path.startswith(p) for p in allowed_prefixes):
        return f"Escrita não permitida em '{path}'. Paths permitidos: {allowed_prefixes}"

    full_path = BASE_DIR / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Backup do ficheiro original
        if full_path.exists():
            backup_path = full_path.with_suffix(full_path.suffix + ".bak")
            backup_path.write_text(full_path.read_text(encoding="utf-8"), encoding="utf-8")

        full_path.write_text(content, encoding="utf-8")
        return f"✅ Ficheiro '{path}' actualizado com sucesso.\nDescrição: {description}\nBackup guardado em {path}.bak"
    except Exception as e:
        return f"Erro ao escrever {path}: {str(e)}"


def _tool_run_backtest(universe: str, start_date: str, end_date: str, entry_mode: str) -> str:
    try:
        # Importar dependências
        sys.path.insert(0, str(BASE_DIR))
        importlib.invalidate_caches()

        # Reimportar a estratégia (pode ter sido editada)
        if "engine.strategies.ep_strategy" in sys.modules:
            del sys.modules["engine.strategies.ep_strategy"]

        from engine.data_feed import DataFeed
        from engine.backtester import Backtester, BacktestConfig
        from engine.strategies.ep_strategy import EpisodicPivotStrategy
        from config import POLYGON_API_KEY

        # Resolver universo
        tickers = _resolve_universe(universe)
        if not tickers:
            return "Universo vazio ou não reconhecido: " + universe

        # Datas
        from datetime import timedelta
        end   = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.utcnow()
        start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else end - timedelta(days=365)

        config = BacktestConfig(
            tickers=tickers,
            start_date=start,
            end_date=end,
            initial_capital=10000,
            entry_mode=entry_mode,
        )

        feed    = DataFeed(polygon_key=POLYGON_API_KEY)
        summary = Backtester(feed, EpisodicPivotStrategy()).run(config)
        result  = summary.to_dict()

        # Formatar resultado legível
        lines = [
            f"=== BACKTEST RESULTS ===",
            f"Universo: {universe} ({len(tickers)} tickers)",
            f"Período: {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}",
            f"Modo entrada: {entry_mode}",
            f"",
            f"Trades: {result['total_trades']}",
            f"Win Rate: {result['win_rate']}%",
            f"Avg Win: {result['avg_win_pct']}%",
            f"Avg Loss: {result['avg_loss_pct']}%",
            f"Profit Factor: {result['profit_factor']}",
            f"Total Return: {result['total_return_pct']}%",
            f"Max Drawdown: {result['max_drawdown_pct']}%",
            f"Avg Hold: {result['avg_hold_days']} dias",
        ]

        # Breakdown
        breakdown = result.get("breakdown", {})
        if breakdown:
            lines.append("")
            lines.append("=== BREAKDOWN ===")
            for dim, groups in breakdown.items():
                lines.append(f"\n{dim}:")
                for group, stats in groups.items():
                    if stats.get("trades", 0) > 0:
                        lines.append(
                            f"  {group}: {stats['trades']} trades | "
                            f"WR {stats['win_rate']}% | "
                            f"Avg {stats['avg_pnl']}% | "
                            f"PF {stats['profit_factor']}"
                        )

        return "\n".join(lines)

    except Exception as e:
        logger.error("Erro run_backtest: " + str(e))
        return f"Erro ao correr backtest: {str(e)}"


def _resolve_universe(universe: str) -> list:
    """Resolve o nome do universo para lista de tickers."""
    universe_lower = universe.lower()

    # Se contém vírgulas, é uma lista directa
    if "," in universe:
        return [t.strip().upper() for t in universe.split(",") if t.strip()]

    try:
        sys.path.insert(0, str(BASE_DIR))
        from universes import DASHBOARD_UNIVERSES
        for name, tickers in DASHBOARD_UNIVERSES.items():
            if universe_lower in name.lower() or universe_lower in ["principal", "main"]:
                if "principal" in name.lower() or "54" in name:
                    return tickers
        # Fallback: primeiro universo
        if DASHBOARD_UNIVERSES:
            return list(DASHBOARD_UNIVERSES.values())[0]
    except Exception:
        pass

    return []


def _tool_update_knowledge(lesson: str, source: str, impact: str) -> str:
    path = BASE_DIR / "knowledge" / "ep_strategy.json"
    if not path.exists():
        return "Ficheiro knowledge/ep_strategy.json não encontrado."

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "lessons_learned" not in data:
            data["lessons_learned"] = []

        data["lessons_learned"].append({
            "date":    datetime.utcnow().strftime("%Y-%m-%d"),
            "source":  source,
            "lesson":  lesson,
            "impact":  impact,
        })

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"✅ Lição adicionada ao knowledge JSON.\nTotal de lições: {len(data['lessons_learned'])}"
    except Exception as e:
        return f"Erro ao actualizar knowledge: {str(e)}"


# ── Agente principal ──────────────────────────────────────────────────────────

class TuningAgent:
    """
    Agente de afinação da estratégia EP.
    Usa tool use para ler/escrever ficheiros e correr backtests.
    """

    SYSTEM_PROMPT = """És o agente de afinação da estratégia Episodic Pivot do sistema Integral Trading.

## O teu papel

Tens acesso directo aos ficheiros do projecto e ao backtester. Quando o utilizador pede uma afinação:

1. **Lês** o ficheiro relevante para perceber o estado actual
2. **Propões** a alteração com justificação clara baseada em dados
3. **Escreves** o ficheiro alterado
4. **Corres** o backtest para validar
5. **Analisas** os resultados e sugeres próximos passos
6. **Actualizas** o knowledge JSON com as lições aprendidas

## REGRAS CRÍTICAS

- Usa NO MÁXIMO 3 ferramentas por resposta — não encadees mais de 3 chamadas seguidas
- Depois de correr um backtest, PARA e apresenta os resultados ao utilizador
- Não corras múltiplos backtests em sequência sem mostrar resultados primeiro
- Se precisas de mais informação, pergunta ao utilizador em vez de adivinhar
- Responde SEMPRE em português europeu

## Princípios de afinação

- Baseia todas as decisões em dados dos backtests
- Altera um parâmetro de cada vez
- Compara sempre com a versão anterior
- Documenta cada iteração no knowledge JSON
"""

    def __init__(self):
        self._history = []

    def chat(self, user_message: str, on_tool_use=None) -> str:
        """
        Envia mensagem ao agente e executa ferramentas automaticamente.
        on_tool_use: callback opcional chamado quando uma ferramenta é executada
                     assinatura: on_tool_use(tool_name, tool_input, result)
        """
        if not ANTHROPIC_API_KEY:
            return "Chave ANTHROPIC_API_KEY não configurada."

        self._history.append({"role": "user", "content": user_message})

        # Loop agentic
        max_iterations = 15
        iteration      = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                response = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type":      "application/json",
                        "x-api-key":         ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": CLAUDE_MODEL_FAST,
                        "max_tokens": MAX_TOKENS,
                        "system":     self.SYSTEM_PROMPT,
                        "tools":      TOOLS,
                        "messages":   self._history,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()

            except Exception as e:
                error_msg = f"Erro na API: {str(e)}"
                logger.error(error_msg)
                return error_msg

            stop_reason = data.get("stop_reason")
            content     = data.get("content", [])

            # Adicionar resposta ao histórico
            self._history.append({"role": "assistant", "content": content})

            # Se parou — resposta final
            if stop_reason == "end_turn":
                final_text = ""
                for block in content:
                    if block.get("type") == "text":
                        final_text += block["text"]
                return final_text

            # Se usou ferramentas — executar e continuar
            if stop_reason == "tool_use":
                tool_results = []

                for block in content:
                    if block.get("type") != "tool_use":
                        continue

                    tool_name  = block["name"]
                    tool_input = block["input"]
                    tool_id    = block["id"]

                    logger.info(f"Ferramenta: {tool_name} | Input: {json.dumps(tool_input)[:200]}")

                    result = _execute_tool(tool_name, tool_input)

                    if on_tool_use:
                        on_tool_use(tool_name, tool_input, result)

                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": tool_id,
                        "content":     result,
                    })

                # Enviar resultados das ferramentas de volta
                self._history.append({
                    "role":    "user",
                    "content": tool_results,
                })
                continue

            # Stop reason inesperado
            break

        return "Agente atingiu o limite de iterações sem resposta final."

    def clear_history(self):
        self._history = []

    def get_history(self) -> list:
        return self._history
