"""
Patches para integrar o EconomicCalendar no sistema NCI.

Aplicar no servidor:
  python3 apply_calendar_patches.py
"""

# ── Patch 1: NCISignal — adicionar campos fundamentais ────────────────────────

NCI_SIGNAL_PATCH = '''
    # Campos adicionados pelo EconomicCalendar
    fundamental_risk:   str = "NONE"   # HIGH / MEDIUM / LOW / NONE
    fundamental_block:  bool = False   # True = bloquear entrada
    fundamental_bias:   str = ""       # BULLISH / BEARISH / UNCERTAIN
    fundamental_events: list = field(default_factory=list)
    fundamental_text:   str = ""       # contexto para prompt'''

# ── Patch 2: to_dict() do NCISignal — incluir campos fundamentais ─────────────

NCI_DICT_PATCH_OLD = '''            "alerts":             self.alerts,
        }'''

NCI_DICT_PATCH_NEW = '''            "alerts":             self.alerts,
            "fundamental_risk":   self.fundamental_risk,
            "fundamental_block":  self.fundamental_block,
            "fundamental_bias":   self.fundamental_bias,
            "fundamental_text":   self.fundamental_text,
        }'''

# ── Patch 3: NCIAnalyzer — aceitar calendar opcional ─────────────────────────

ANALYZER_INIT_OLD = '''    def __init__(self, feed, config_path: Path = _CONFIG_PATH):
        self.feed = feed
        self.cfg  = self._load_config(config_path)'''

ANALYZER_INIT_NEW = '''    def __init__(self, feed, config_path: Path = _CONFIG_PATH,
                 calendar=None):
        self.feed     = feed
        self.cfg      = self._load_config(config_path)
        self.calendar = calendar  # EconomicCalendar opcional'''

# ── Patch 4: analyze() — enriquecer com dados fundamentais ───────────────────

ANALYZE_OLD = '''        return self._build_signal(ticker, daily_view, h4_view, h1_view)'''

ANALYZE_NEW = '''        signal = self._build_signal(ticker, daily_view, h4_view, h1_view)

        # Enriquecer com contexto fundamental (se calendar disponível)
        if self.calendar and signal.direction != "NONE":
            try:
                risk = self.calendar.get_asset_risk(ticker, hours_ahead=48)
                signal.fundamental_risk   = risk.risk_level
                signal.fundamental_block  = risk.in_block_zone
                signal.fundamental_bias   = risk.direction_bias or ""
                signal.fundamental_events = [e.to_dict() for e in risk.events]
                signal.fundamental_text   = risk.context_text

                # Ajustar alertas
                if risk.risk_level == "HIGH" and not risk.in_block_zone:
                    signal.alerts.append("⚠️ Evento HIGH IMPACT próximo — aguardar")
                elif risk.in_block_zone:
                    signal.alerts.append("🔴 BLOQUEADO — evento a decorrer agora")

                # Se evento contradiz direcção técnica
                if risk.direction_bias == "UNCERTAIN":
                    signal.alerts.append("⚡ Evento pode reverter direcção — cuidado")

            except Exception as _e:
                import logging as _log
                _log.getLogger(__name__).warning("Calendar error: " + str(_e))

        return signal'''


if __name__ == "__main__":
    import ast

    # Aplicar patches ao nci_analyzer.py
    path = "engine/nci_analyzer.py"
    content = open(path).read()

    patches = [
        # Init com calendar
        (ANALYZER_INIT_OLD, ANALYZER_INIT_NEW, "NCIAnalyzer.__init__ com calendar"),
        # analyze() com enriquecimento
        (ANALYZE_OLD, ANALYZE_NEW, "analyze() enriquecer com fundamental"),
        # to_dict() do NCISignal
        (NCI_DICT_PATCH_OLD, NCI_DICT_PATCH_NEW, "NCISignal.to_dict() campos fundamentais"),
    ]

    for old, new, desc in patches:
        if old in content:
            content = content.replace(old, new, 1)
            print("✅ " + desc)
        else:
            print("⚠️  Não encontrado: " + desc)

    # Adicionar campos ao NCISignal dataclass
    signal_field_anchor = "    setup_description: str"
    if signal_field_anchor in content and "fundamental_risk" not in content:
        content = content.replace(
            signal_field_anchor,
            signal_field_anchor + "\n" + NCI_SIGNAL_PATCH
        )
        print("✅ NCISignal — campos fundamentais adicionados")
    elif "fundamental_risk" in content:
        print("ℹ️  NCISignal — campos já existem")

    ast.parse(content)
    open(path, "w").write(content)
    print("\nnci_analyzer.py actualizado")
