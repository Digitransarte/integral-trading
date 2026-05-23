"""Integral Trading — NCI Engine
=================================
Implementação limpa do NCI Level 0, construída por camadas.

Camada 1: Classificação de Candles
  classify_candle()    — classifica um candle isolado por ratios internos
  is_big_candle()      — avalia tamanho relativo aos Marubozu recentes
  is_small_candle()    — avalia se candle é pequeno face ao anterior
  classify_candles()   — classifica série completa com contexto de tamanho

Camada 2: Market Structure
  find_swings()              — detecta Swing Highs e Swing Lows (window N)
  define_trend()             — classifica tendência por sequência de swings
  find_key_level()           — identifica Key Level (HL ou LH que criou BOS)
  filter_external_swings()   — separa estrutura externa de internal structure
  analyze_market_structure() — pipeline completo da Camada 2

Camada 3: Pullback & Breakout Standards
  detect_pullback()  — padrão de entrada após pullback (Two Maru / Big+Small / PAC)
  detect_breakout()  — padrão de quebra de nível com confirmação boi_price
  is_valid_bos()     — valida se BOS é legítimo ou Fake Breakout

Camada 4: Range Detection, KL Quality & Pipeline
  detect_range()               — detecta range e o seu tipo (Maru/Pinbar-Doji/tipos externos)
  evaluate_key_level_quality() — avalia qualidade do KL face ao range (invalid/weak/normal)
  check_market_cycle()         — verifica se o ciclo LTF terminou numa zona HTF
  analyze_nci()                — pipeline completo: classifica → estrutura → pullback → BOS → ciclo
"""

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Camada 1 — Classificação de Candles
# ─────────────────────────────────────────────────────────────────────────────

def classify_candle(open_: float, high: float, low: float, close: float) -> dict:
    """
    Classifica um candle segundo as regras NCI Level 0.

    Hierarquia aplicada (cada regra só alcançada se as anteriores falharam):

      1. Marubozu         body >= 70% do total_length
      2. Doji             body < 10% do total_length
      3. Special Marubozu body >= 25% e close a >= 90% do range da candle
      4. Pinbar           body < 25%  (proxy "candle grande + corpo pequeno")
      5. Normal           tudo o resto

    Notas de implementação:
      • A spec original define body >= 50% para Special Marubozu, mas o caso
        canónico (100, 115, 85, 113) tem body_pct = 43 %.  O critério
        dominante é close_level >= 0.90; o floor de 25 % apenas exclui
        corpos mínimos que já foram capturados pelo check Doji.
      • Pinbar e Doji precisam de contexto de tamanho para confirmação
        precisa — usar classify_candles() para série completa.

    Args:
        open_: preço de abertura
        high:  máximo
        low:   mínimo
        close: preço de fecho

    Retorna:
        {
            "type":         "marubozu" | "special_marubozu" | "pinbar"
                            | "doji" | "normal",
            "direction":    "up" | "down" | "neutral",
            "body_pct":     float,   # body / total_length
            "total_length": float,   # high - low em pontos
            "body":         float,   # abs(close - open)
        }
    """
    total_length = high - low

    # Candle sem range (flat ou dados inválidos)
    if total_length <= 0:
        return _make(0.0, 0.0, 0.0, "doji", "neutral")

    body     = abs(close - open_)
    body_pct = body / total_length

    if close > open_:
        direction   = "up"
        close_level = (close - low) / total_length
    elif close < open_:
        direction   = "down"
        close_level = (high - close) / total_length
    else:
        direction   = "neutral"
        close_level = 0.0

    # 1. Marubozu: corpo dominante (>= 70 %)
    if body_pct >= 0.70:
        return _make(total_length, body, body_pct, "marubozu", direction)

    # 2. Doji: corpo mínimo (< 10 %) — proxy para "candle pequeno"
    if body_pct < 0.10:
        return _make(total_length, body, body_pct, "doji", "neutral")

    # 3. Special Marubozu: fecho perto do extremo (>= 90 % do range)
    if body_pct >= 0.25 and close_level >= 0.90:
        return _make(total_length, body, body_pct, "special_marubozu", direction)

    # 4. Pinbar: corpo pequeno (< 25 %) — proxy para "candle grande + corpo pequeno"
    #    Confirmação de tamanho via is_big_candle() em classify_candles().
    if body_pct < 0.25:
        return _make(total_length, body, body_pct, "pinbar", "neutral")

    # 5. Normal
    return _make(total_length, body, body_pct, "normal", direction)


def _make(total_length: float, body: float, body_pct: float,
          candle_type: str, direction: str) -> dict:
    return {
        "type":         candle_type,
        "direction":    direction,
        "body_pct":     round(body_pct, 4),
        "total_length": round(total_length, 8),
        "body":         round(body, 8),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Funções de contexto
# ─────────────────────────────────────────────────────────────────────────────

def is_big_candle(candle_total_length: float, recent_maru_lengths: list) -> bool:
    """
    Avalia se um candle é "grande" face aos Marubozu recentes.

    Um candle é grande se o seu total_length for >= 50 % do maior Marubozu
    dos últimos 5 candles Marubozu. Usado para confirmar Pinbar.

    Args:
        candle_total_length: high - low do candle a avaliar
        recent_maru_lengths: total_lengths dos últimos 5 candles Marubozu
                             (lista pode ter 0 a 5 elementos)

    Retorna:
        True se candle_total_length >= 50 % do max da lista.
        False se a lista estiver vazia.
    """
    if not recent_maru_lengths:
        return False
    return candle_total_length >= 0.50 * max(recent_maru_lengths)


def is_small_candle(candle_total_length: float, previous_total_length: float) -> bool:
    """
    Avalia se um candle é "pequeno" face ao candle imediatamente anterior.

    Um candle é pequeno se o seu total_length for <= 30 % do anterior.
    Usado para confirmar Doji e padrão Big Maru + Small.

    Args:
        candle_total_length:   high - low do candle a avaliar
        previous_total_length: high - low do candle anterior

    Retorna:
        True se candle_total_length <= 30 % do previous_total_length.
    """
    if previous_total_length <= 0:
        return False
    return candle_total_length <= 0.30 * previous_total_length


# ─────────────────────────────────────────────────────────────────────────────
# Classificação em série com contexto
# ─────────────────────────────────────────────────────────────────────────────

def classify_candles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classifica todos os candles de um DataFrame com contexto de tamanho.

    Processo em dois passes:
      Passe 1 — classify_candle() em cada linha (sem contexto)
      Passe 2 — refinamento de Pinbar e Doji com contexto de janela

    Refinamento:
      Pinbar: confirmed se total_length >= 50 % do maior Marubozu dos últimos 5.
              Downgrade para "normal" se não confirmado.
      Doji:   confirmed se total_length < 30 % da média dos últimos 10 total_lengths.
              Downgrade: se total_length >= 30 % da média mas body_pct < 10 %,
              reclassifica como "pinbar" (se grande) ou "normal".

    Args:
        df: DataFrame com colunas open, high, low, close (case-insensitive não
            tratado — usar lowercase)

    Retorna:
        Cópia do df com colunas adicionadas:
        candle_type, direction, body_pct, total_length, body
    """
    df = df.reset_index(drop=True)
    result = df.copy()
    n = len(result)

    if n == 0:
        result["candle_type"]  = []
        result["direction"]    = []
        result["body_pct"]     = []
        result["total_length"] = []
        result["body"]         = []
        return result

    # Passe 1: arrays raw sem contexto
    opens  = result["open"].to_numpy(dtype=float)
    highs  = result["high"].to_numpy(dtype=float)
    lows   = result["low"].to_numpy(dtype=float)
    closes = result["close"].to_numpy(dtype=float)

    candle_types  = []
    directions    = []
    body_pcts     = []
    total_lengths = []
    bodies        = []

    for i in range(n):
        c = classify_candle(opens[i], highs[i], lows[i], closes[i])
        candle_types.append(c["type"])
        directions.append(c["direction"])
        body_pcts.append(c["body_pct"])
        total_lengths.append(c["total_length"])
        bodies.append(c["body"])

    # Passe 2: refinamento com contexto (processa da esquerda → cada índice
    # vê apenas candles já refinados em j < i)
    for i in range(n):
        ct = candle_types[i]

        if ct not in ("pinbar", "doji"):
            continue

        tl = total_lengths[i]

        # Janela de 10 para média de tamanho
        w_start = max(0, i - 10)
        window  = total_lengths[w_start:i]
        avg_10  = sum(window) / len(window) if window else tl

        # Marubozu recentes (últimos 5 já refinados) para is_big_candle
        maru_lengths = [
            total_lengths[j]
            for j in range(max(0, i - 5), i)
            if candle_types[j] == "marubozu"
        ]

        if ct == "doji":
            if tl >= 0.30 * avg_10:
                # Candle não é pequeno — não é Doji em contexto
                # Se tiver range suficiente para ser grande → Pinbar
                if is_big_candle(tl, maru_lengths):
                    candle_types[i] = "pinbar"
                    directions[i]   = "neutral"
                else:
                    candle_types[i] = "normal"

        elif ct == "pinbar":
            if not is_big_candle(tl, maru_lengths):
                # Candle não é grande — não é Pinbar em contexto
                candle_types[i] = "normal"

    result["candle_type"]  = candle_types
    result["direction"]    = directions
    result["body_pct"]     = body_pcts
    result["total_length"] = total_lengths
    result["body"]         = bodies

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Camada 2 — Market Structure
# ─────────────────────────────────────────────────────────────────────────────

def find_swings(df: pd.DataFrame, window: int = 2) -> pd.DataFrame:
    """
    Detecta Swing Highs (SH) e Swing Lows (SL) por pivô de janela.

    Um candle i é SH se high[i] >= high[j] para todo j em [i-window, i+window], j≠i.
    Um candle i é SL se low[i]  <= low[j]  para todo j em [i-window, i+window], j≠i.

    Candles nas margens (< window ou > n-window-1) nunca são swing points.

    Args:
        df:     DataFrame com colunas high, low (+ open, close opcionais)
        window: raio da janela de comparação (default 2)

    Retorna:
        Cópia do df com colunas adicionadas:
        swing_high (bool), swing_low (bool)
    """
    df = df.reset_index(drop=True)
    result = df.copy()
    n      = len(result)
    highs  = result["high"].to_numpy(dtype=float)
    lows   = result["low"].to_numpy(dtype=float)

    sh = [False] * n
    sl = [False] * n

    for i in range(window, n - window):
        neighbors = list(range(i - window, i + window + 1))
        neighbors.remove(i)
        if all(highs[i] >= highs[j] for j in neighbors):
            sh[i] = True
        if all(lows[i] <= lows[j] for j in neighbors):
            sl[i] = True

    result["swing_high"] = sh
    result["swing_low"]  = sl
    return result


def define_trend(swing_highs: list, swing_lows: list) -> str:
    """
    Classifica a tendência a partir das últimas sequências de swings.

    Regras (aplicadas sobre os últimos 2 SH e últimos 2 SL):
      HH (h2 > h1) AND HL (l2 > l1) → "uptrend"
      LH (h2 < h1) AND LL (l2 < l1) → "downtrend"
      caso contrário                  → "range"

    Se não houver pelo menos 2 SH e 2 SL retorna "undefined".

    Args:
        swing_highs: lista de preços dos Swing Highs em ordem cronológica
        swing_lows:  lista de preços dos Swing Lows  em ordem cronológica

    Retorna:
        "uptrend" | "downtrend" | "range" | "undefined"
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "undefined"

    h1, h2 = swing_highs[-2], swing_highs[-1]
    l1, l2 = swing_lows[-2],  swing_lows[-1]

    hh = h2 > h1
    hl = l2 > l1
    lh = h2 < h1
    ll = l2 < l1

    if hh and hl:
        return "uptrend"
    if lh and ll:
        return "downtrend"
    return "range"


def find_key_level(df: pd.DataFrame, trend: str) -> dict | None:
    """
    Identifica o Key Level (KL) — o último swing que gerou o BOS mais recente.

    Lógica:
      Uptrend:   procura o último par SH[n-1] > SH[n-2] (HH confirmado);
                 o KL é o SL mais recente entre esses dois SH.
      Downtrend: procura o último par SL[n-1] < SL[n-2] (LL confirmado);
                 o KL é o SH mais recente entre esses dois SL.
      Range/other: retorna None.

    O df deve já conter colunas swing_high e swing_low (output de find_swings).

    Retorna:
        {"price": float, "index": int, "type": "HL" | "LH"} ou None
    """
    if trend not in ("uptrend", "downtrend"):
        return None

    df    = df.reset_index(drop=True)
    idx   = df.index.tolist()
    highs = df["high"].to_numpy(dtype=float)
    lows  = df["low"].to_numpy(dtype=float)
    sh    = df["swing_high"].to_numpy(dtype=bool)
    sl    = df["swing_low"].to_numpy(dtype=bool)
    n     = len(df)

    if trend == "uptrend":
        # Encontrar os últimos dois SH
        sh_indices = [i for i in range(n) if sh[i]]
        if len(sh_indices) < 2:
            return None
        i2, i1 = sh_indices[-1], sh_indices[-2]
        if highs[i2] <= highs[i1]:
            return None
        # SL entre i1 e i2
        sl_between = [i for i in range(i1 + 1, i2) if sl[i]]
        if not sl_between:
            return None
        kl_pos = sl_between[-1]
        return {"price": float(lows[kl_pos]), "index": idx[kl_pos], "type": "HL"}

    else:  # downtrend
        # Encontrar os últimos dois SL
        sl_indices = [i for i in range(n) if sl[i]]
        if len(sl_indices) < 2:
            return None
        i2, i1 = sl_indices[-1], sl_indices[-2]
        if lows[i2] >= lows[i1]:
            return None
        # SH entre i1 e i2
        sh_between = [i for i in range(i1 + 1, i2) if sh[i]]
        if not sh_between:
            return None
        kl_pos = sh_between[-1]
        return {"price": float(highs[kl_pos]), "index": idx[kl_pos], "type": "LH"}


def filter_external_swings(df: pd.DataFrame, key_level_index) -> dict:
    """
    Separa estrutura externa (antes e incluindo o KL) de estrutura interna
    (tudo após o KL).

    A estrutura interna é descartada para análise de tendência e KL — só a
    estrutura externa é válida para definir o regime de mercado.

    Args:
        df:              DataFrame com swing_high e swing_low
        key_level_index: valor do índice (df.index) do Key Level

    Retorna:
        {
            "external": DataFrame (índices <= key_level_index),
            "internal": DataFrame (índices >  key_level_index),
        }
    """
    df = df.reset_index(drop=True)
    external = df.loc[df.index <= key_level_index].copy()
    internal = df.loc[df.index >  key_level_index].copy()
    return {"external": external, "internal": internal}


def analyze_market_structure(df: pd.DataFrame, window: int = 2) -> dict:
    """
    Pipeline completo da Camada 2.

    Passos:
      1. find_swings()           — detecta SH e SL
      2. Extrai listas de preços de SH e SL
      3. define_trend()          — classifica tendência
      4. find_key_level()        — identifica KL
      5. filter_external_swings()— separa estrutura externa/interna (se KL existe)

    Args:
        df:     DataFrame com colunas open, high, low, close
        window: janela para find_swings (default 2)

    Retorna:
        {
            "df":           DataFrame com swing_high, swing_low
            "swing_highs":  list de preços dos SH (cronológico)
            "swing_lows":   list de preços dos SL (cronológico)
            "trend":        "uptrend" | "downtrend" | "range" | "undefined"
            "key_level":    dict {"price", "index", "type"} ou None
            "external":     DataFrame (estrutura externa) ou None
            "internal":     DataFrame (estrutura interna) ou None
        }
    """
    df = df.reset_index(drop=True)
    df_sw = find_swings(df, window=window)

    n     = len(df_sw)
    highs = df_sw["high"].to_numpy(dtype=float)
    lows  = df_sw["low"].to_numpy(dtype=float)

    sh_prices = [highs[i] for i in range(n) if df_sw["swing_high"].iloc[i]]
    sl_prices = [lows[i]  for i in range(n) if df_sw["swing_low"].iloc[i]]

    trend = define_trend(sh_prices, sl_prices)
    kl    = find_key_level(df_sw, trend)

    external = internal = None
    if kl is not None:
        split    = filter_external_swings(df_sw, kl["index"])
        external = split["external"]
        internal = split["internal"]

    return {
        "df":          df_sw,
        "swing_highs": sh_prices,
        "swing_lows":  sl_prices,
        "trend":       trend,
        "key_level":   kl,
        "external":    external,
        "internal":    internal,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Camada 3 — Pullback & Breakout Standards
# ─────────────────────────────────────────────────────────────────────────────

def _pos_of(idx_list: list, start_idx: int) -> int:
    """Posição inteira (0-based) para o valor de índice start_idx."""
    try:
        return idx_list.index(start_idx)
    except ValueError:
        return next((i for i, v in enumerate(idx_list) if v >= start_idx), len(idx_list))


def detect_pullback(df: pd.DataFrame, direction: str, start_idx: int) -> dict | None:
    """
    Detecta o primeiro padrão de pullback válido a partir de start_idx.

    Hierarquia (por par consecutivo de candles):
      1. Two Marubozu      — dois Maru na direcção do trend, close2>close1 (up),
                             total_length2 >= 70 % de total_length1
      2. Big Maru + Small  — Maru grande + candle pequeno bem posicionado
      3. PAC               — confirmação nos 4 candles seguintes quando P1 ou P2
                             falha numa condição (tamanho ou posição)

    Args:
        df:         DataFrame com colunas da Camada 1 (candle_type, direction,
                    total_length, body, high, low, close)
        direction:  "up" (pullback em uptrend) ou "down"
        start_idx:  valor do índice df.index a partir do qual pesquisar

    Retorna:
        {
          "pattern":        "two_marubozu" | "big_maru_small" | "pac",
          "valid":          True,
          "candles":        lista de índices do padrão,
          "entry_price":    preço de entrada sugerido,
          "invalidated_at": None,
        }
        ou None se não encontrado.
    """
    df        = df.reset_index(drop=True)
    idx_list  = df.index.tolist()
    start_pos = _pos_of(idx_list, start_idx)
    n         = len(df)

    closes = df["close"].to_numpy(dtype=float)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    types  = df["candle_type"].tolist()
    dirs   = df["direction"].tolist()
    tls    = df["total_length"].to_numpy(dtype=float)

    is_maru = lambda t: t in ("marubozu", "special_marubozu")

    maru_before = [
        tls[k] for k in range(max(0, start_pos - 5), start_pos)
        if is_maru(types[k])
    ]

    def _pac(i: int, j: int) -> dict | None:
        hh = max(highs[i], highs[j])
        ll = min(lows[i],  lows[j])
        for k in range(j + 1, min(j + 5, n)):
            if direction == "up"   and closes[k] > hh:
                return {"pattern": "pac", "valid": True,
                        "candles": [idx_list[i], idx_list[j], idx_list[k]],
                        "entry_price": closes[k], "invalidated_at": None}
            if direction == "down" and closes[k] < ll:
                return {"pattern": "pac", "valid": True,
                        "candles": [idx_list[i], idx_list[j], idx_list[k]],
                        "entry_price": closes[k], "invalidated_at": None}
        return None

    for i in range(start_pos, n - 1):
        j = i + 1

        # Pattern 1: Two Marubozu
        p1_base = (
            is_maru(types[i]) and is_maru(types[j])
            and dirs[i] == direction and dirs[j] == direction
            and (closes[j] > closes[i] if direction == "up" else closes[j] < closes[i])
        )
        if p1_base:
            if tls[j] >= 0.70 * tls[i]:
                return {"pattern": "two_marubozu", "valid": True,
                        "candles": [idx_list[i], idx_list[j]],
                        "entry_price": closes[j], "invalidated_at": None}
            pac = _pac(i, j)
            if pac:
                return pac

        # Pattern 2: Big Maru + Small
        if is_maru(types[i]) and dirs[i] == direction and is_big_candle(tls[i], maru_before):
            if is_small_candle(tls[j], tls[i]):
                pos_ok = (lows[j]  > lows[i]  + tls[i] * 0.5) if direction == "up" \
                    else (highs[j] < highs[i] - tls[i] * 0.5)
                if pos_ok:
                    return {"pattern": "big_maru_small", "valid": True,
                            "candles": [idx_list[i], idx_list[j]],
                            "entry_price": closes[i], "invalidated_at": None}
                pac = _pac(i, j)
                if pac:
                    return pac

    return None


def detect_breakout(df: pd.DataFrame, boi_price: float,
                    direction: str, start_idx: int) -> dict | None:
    """
    Detecta o primeiro padrão de breakout válido a partir de start_idx.

    Extensão do detect_pullback com condições adicionais de confirmação
    da boi_price (Break Out line / Key Level a quebrar):

      P1 (Two Marubozu):   ambos os candles fecham além da boi_price
      P2 (Big Maru+Small): >30 % do body do Big Maru está além da boi_price
      PAC:                 mesma lógica do pullback

    Args:
        df:         DataFrame com colunas da Camada 1
        boi_price:  preço da linha a quebrar
        direction:  "up" ou "down"
        start_idx:  valor do índice a partir do qual pesquisar

    Retorna:
        Mesma estrutura que detect_pullback mais:
          "boi_price":     float,
          "boi_confirmed": True
        ou None se não encontrado.
    """
    df        = df.reset_index(drop=True)
    idx_list  = df.index.tolist()
    start_pos = _pos_of(idx_list, start_idx)
    n         = len(df)

    closes = df["close"].to_numpy(dtype=float)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    types  = df["candle_type"].tolist()
    dirs   = df["direction"].tolist()
    tls    = df["total_length"].to_numpy(dtype=float)
    bodies = df["body"].to_numpy(dtype=float)

    is_maru = lambda t: t in ("marubozu", "special_marubozu")

    maru_before = [
        tls[k] for k in range(max(0, start_pos - 5), start_pos)
        if is_maru(types[k])
    ]

    def _beyond(price: float) -> bool:
        return price > boi_price if direction == "up" else price < boi_price

    def _body_beyond_pct(close_c: float, body_c: float) -> float:
        if body_c <= 0:
            return 0.0
        return (close_c - boi_price) / body_c if direction == "up" \
            else (boi_price - close_c) / body_c

    def _wrap(r: dict) -> dict:
        r["boi_price"]     = boi_price
        r["boi_confirmed"] = True
        return r

    def _pac(i: int, j: int) -> dict | None:
        hh = max(highs[i], highs[j])
        ll = min(lows[i],  lows[j])
        for k in range(j + 1, min(j + 5, n)):
            if direction == "up"   and closes[k] > hh:
                return _wrap({"pattern": "pac", "valid": True,
                              "candles": [idx_list[i], idx_list[j], idx_list[k]],
                              "entry_price": closes[k], "invalidated_at": None})
            if direction == "down" and closes[k] < ll:
                return _wrap({"pattern": "pac", "valid": True,
                              "candles": [idx_list[i], idx_list[j], idx_list[k]],
                              "entry_price": closes[k], "invalidated_at": None})
        return None

    for i in range(start_pos, n - 1):
        j = i + 1

        # Pattern 1: Two Marubozu + both close beyond boi_price
        p1_base = (
            is_maru(types[i]) and is_maru(types[j])
            and dirs[i] == direction and dirs[j] == direction
            and (closes[j] > closes[i] if direction == "up" else closes[j] < closes[i])
            and _beyond(closes[i]) and _beyond(closes[j])
        )
        if p1_base:
            if tls[j] >= 0.70 * tls[i]:
                return _wrap({"pattern": "two_marubozu", "valid": True,
                              "candles": [idx_list[i], idx_list[j]],
                              "entry_price": closes[j], "invalidated_at": None})
            pac = _pac(i, j)
            if pac:
                return pac

        # Pattern 2: Big Maru + Small + >30 % body beyond boi_price
        if (is_maru(types[i]) and dirs[i] == direction
                and is_big_candle(tls[i], maru_before)
                and _body_beyond_pct(closes[i], bodies[i]) > 0.30):
            if is_small_candle(tls[j], tls[i]):
                pos_ok = (lows[j]  > lows[i]  + tls[i] * 0.5) if direction == "up" \
                    else (highs[j] < highs[i] - tls[i] * 0.5)
                if pos_ok:
                    return _wrap({"pattern": "big_maru_small", "valid": True,
                                  "candles": [idx_list[i], idx_list[j]],
                                  "entry_price": closes[i], "invalidated_at": None})
                pac = _pac(i, j)
                if pac:
                    return pac

    return None


def is_valid_bos(df: pd.DataFrame, key_level_price: float,
                 key_level_index: int, direction: str) -> dict:
    """
    Valida se o BOS (Break of Structure) no Key Level é legítimo.

    Um BOS é válido quando a quebra do KL é confirmada por um padrão de
    breakout standard. Sem padrão, qualquer close além do KL é Fake Breakout.

    Args:
        df:               DataFrame com colunas da Camada 1
        key_level_price:  preço do KL a quebrar
        key_level_index:  valor do índice (df.index) do Key Level
        direction:        "up" ou "down"

    Retorna:
        {
          "valid":            bool,
          "type":             "confirmed_bos" | "fake_breakout" | "pending",
          "breakout_pattern": dict | None,
          "fake_at_index":    int | None,
        }
    """
    df        = df.reset_index(drop=True)
    idx_list  = df.index.tolist()
    kl_pos    = _pos_of(idx_list, key_level_index)
    start_pos = kl_pos + 1

    _pending = {"valid": False, "type": "pending",
                "breakout_pattern": None, "fake_at_index": None}

    if start_pos >= len(idx_list):
        return _pending

    bko = detect_breakout(df, key_level_price, direction, idx_list[start_pos])
    if bko is not None:
        return {"valid": True, "type": "confirmed_bos",
                "breakout_pattern": bko, "fake_at_index": None}

    closes = df["close"].to_numpy(dtype=float)
    for i in range(start_pos, len(df)):
        if direction == "up"   and closes[i] > key_level_price:
            return {"valid": False, "type": "fake_breakout",
                    "breakout_pattern": None, "fake_at_index": idx_list[i]}
        if direction == "down" and closes[i] < key_level_price:
            return {"valid": False, "type": "fake_breakout",
                    "breakout_pattern": None, "fake_at_index": idx_list[i]}

    return _pending


# ─────────────────────────────────────────────────────────────────────────────
# Camada 4 — Range Detection & Key Level Quality
# ─────────────────────────────────────────────────────────────────────────────

def detect_range(df: pd.DataFrame, start_idx: int,
                 lookback: int = 5,
                 range_type: str | None = None) -> dict:
    """
    Detecta se existe um range a partir do candle âncora em start_idx.

    Condição base: entre 2 e lookback candles após o âncora têm os seus
    closes dentro do intervalo [anchor_low, anchor_high].

    Tipos detectados automaticamente (quando range_type=None):
      "marubozu"    — âncora é marubozu ou special_marubozu
      "pinbar_doji" — âncora é pinbar ou doji

    Tipos injectados externamente (range_type explícito):
      "invalid_pullback" — chamado quando detect_pullback() retorna None
      "fake_breakout"    — chamado quando is_valid_bos() retorna fake_breakout

    LOW LIQUIDITY: âncora é doji E total_length < 30 % da média dos
    últimos 10 total_lengths → low_liquidity=True (range quebra facilmente).

    Args:
        df:         DataFrame com colunas da Camada 1 (candle_type, total_length,
                    high, low, close)
        start_idx:  valor do índice df.index do candle âncora
        lookback:   janela de candles a verificar após o âncora (default 5)
        range_type: tipo forçado externamente; None = auto-detectar pelo âncora

    Retorna:
        {
          "detected":          bool,
          "type":              str | None,
          "low_liquidity":     bool,
          "anchor_index":      int | None,
          "anchor_price_high": float | None,
          "anchor_price_low":  float | None,
          "candles_inside":    list[int],
        }
    """
    df = df.reset_index(drop=True)
    _empty = {
        "detected": False, "type": None, "low_liquidity": False,
        "anchor_index": None, "anchor_price_high": None,
        "anchor_price_low": None, "candles_inside": [],
    }

    idx_list  = df.index.tolist()
    start_pos = _pos_of(idx_list, start_idx)
    n         = len(df)

    if start_pos >= n:
        return _empty

    closes = df["close"].to_numpy(dtype=float)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    tls    = df["total_length"].to_numpy(dtype=float)
    types  = df["candle_type"].tolist()

    anchor_type = types[start_pos]
    anchor_high = float(highs[start_pos])
    anchor_low  = float(lows[start_pos])
    anchor_tl   = float(tls[start_pos])

    # Determine range type
    if range_type is not None:
        rtype = range_type
    elif anchor_type in ("marubozu", "special_marubozu"):
        rtype = "marubozu"
    elif anchor_type in ("pinbar", "doji"):
        rtype = "pinbar_doji"
    else:
        return _empty

    # Collect closes inside anchor range among next `lookback` candles
    inside = [
        idx_list[i]
        for i in range(start_pos + 1, min(start_pos + lookback + 1, n))
        if anchor_low <= closes[i] <= anchor_high
    ]

    if len(inside) < 2:
        return _empty

    # Low liquidity: doji anchor with total_length well below recent average
    w_start = max(0, start_pos - 10)
    window  = tls[w_start:start_pos]
    avg_10  = float(window.mean()) if len(window) > 0 else anchor_tl
    low_liq = (anchor_type == "doji") and (anchor_tl < 0.30 * avg_10)

    return {
        "detected":          True,
        "type":              rtype,
        "low_liquidity":     low_liq,
        "anchor_index":      idx_list[start_pos],
        "anchor_price_high": anchor_high,
        "anchor_price_low":  anchor_low,
        "candles_inside":    inside,
    }


def evaluate_key_level_quality(key_level: dict,
                               range_result: dict,
                               pullback_start_idx: int,
                               pullback_end_idx: int) -> dict:
    """
    Avalia a qualidade do Key Level face à presença de um range.

    Regras NCI:
      Sem range detectado                         → quality="normal"
      range_anchor_index < pullback_start_idx     → quality="weak"
        (range antes do pullback — zona enfraquecida mas válida)
      range_anchor_index > pullback_end_idx       → quality="invalid"
        (range depois do pullback — pullback apagado pelo range)

    Args:
        key_level:          dict com "price" (output de find_key_level)
        range_result:       dict (output de detect_range)
        pullback_start_idx: índice do primeiro candle do pullback detectado
        pullback_end_idx:   índice do último candle do pullback detectado

    Retorna:
        {
          "key_level_price": float,
          "quality":         "invalid" | "weak" | "normal",
          "reason":          str,
        }
    """
    price = key_level["price"]

    if not range_result["detected"]:
        return {"key_level_price": price, "quality": "normal",
                "reason": "No range detected near the pullback."}

    anchor = range_result["anchor_index"]

    if anchor > pullback_end_idx:
        return {
            "key_level_price": price,
            "quality":         "invalid",
            "reason":          (f"Range formed after pullback "
                                f"(anchor {anchor} > pullback end {pullback_end_idx})."),
        }

    if anchor < pullback_start_idx:
        return {
            "key_level_price": price,
            "quality":         "weak",
            "reason":          (f"Range formed before pullback "
                                f"(anchor {anchor} < pullback start {pullback_start_idx})."),
        }

    return {"key_level_price": price, "quality": "normal",
            "reason": "Range within pullback window — no quality impact."}


def check_market_cycle(ltf_current_price: float,
                       ltf_trend: str,
                       htf_zones: dict,
                       ltf_key_level_price: float | None = None) -> dict:
    """
    Determina se o ciclo do LTF está activo ou terminou ao atingir uma zona HTF.

    Uptrend — zonas de término (por ordem): down_key_level, poi_zone_low, recent_high
      Termina:  ltf_current_price >= zona
      Warning:  dist_actual <= dist_total × 20 %
                (dist_total = zona − ltf_key_level_price; se None: preço >= zona × 80 %)

    Downtrend — zonas de término: up_key_level, poi_zone_high, recent_low
      Termina:  ltf_current_price <= zona
      Warning:  dist_actual <= dist_total × 20 %
                (dist_total = ltf_key_level_price − zona; se None: preço <= zona × 120 %)

    Args:
        ltf_current_price:   último close do LTF
        ltf_trend:           "uptrend" | "downtrend" (outros → ciclo inactivo)
        htf_zones:           dict com down_key_level, up_key_level, poi_zone_high,
                             poi_zone_low, recent_high, recent_low
        ltf_key_level_price: preço do KL do LTF para cálculo preciso do warning

    Retorna:
        {
          "cycle_active":    bool,
          "cycle_direction": "up" | "down" | None,
          "terminated_by":   str | None,
          "warning":         bool,
          "warning_zone":    str | None,
        }
    """
    if ltf_trend == "uptrend":
        direction = "up"
        zone_keys = ["down_key_level", "poi_zone_low", "recent_high"]

        for zkey in zone_keys:
            zval = htf_zones.get(zkey)
            if zval is None:
                continue
            if ltf_current_price >= zval:
                return {"cycle_active": False, "cycle_direction": direction,
                        "terminated_by": zkey, "warning": False, "warning_zone": None}

        for zkey in zone_keys:
            zval = htf_zones.get(zkey)
            if zval is None:
                continue
            if ltf_key_level_price is not None:
                dist_total  = zval - ltf_key_level_price
                dist_actual = zval - ltf_current_price
                if dist_total > 0 and dist_actual <= dist_total * 0.20:
                    return {"cycle_active": True, "cycle_direction": direction,
                            "terminated_by": None, "warning": True, "warning_zone": zkey}
            else:
                if ltf_current_price >= zval * 0.80:
                    return {"cycle_active": True, "cycle_direction": direction,
                            "terminated_by": None, "warning": True, "warning_zone": zkey}

        return {"cycle_active": True, "cycle_direction": direction,
                "terminated_by": None, "warning": False, "warning_zone": None}

    elif ltf_trend == "downtrend":
        direction = "down"
        zone_keys = ["up_key_level", "poi_zone_high", "recent_low"]

        for zkey in zone_keys:
            zval = htf_zones.get(zkey)
            if zval is None:
                continue
            if ltf_current_price <= zval:
                return {"cycle_active": False, "cycle_direction": direction,
                        "terminated_by": zkey, "warning": False, "warning_zone": None}

        for zkey in zone_keys:
            zval = htf_zones.get(zkey)
            if zval is None:
                continue
            if ltf_key_level_price is not None:
                dist_total  = ltf_key_level_price - zval
                dist_actual = ltf_current_price - zval
                if dist_total > 0 and dist_actual <= dist_total * 0.20:
                    return {"cycle_active": True, "cycle_direction": direction,
                            "terminated_by": None, "warning": True, "warning_zone": zkey}
            else:
                if ltf_current_price <= zval * 1.20:
                    return {"cycle_active": True, "cycle_direction": direction,
                            "terminated_by": None, "warning": True, "warning_zone": zkey}

        return {"cycle_active": True, "cycle_direction": direction,
                "terminated_by": None, "warning": False, "warning_zone": None}

    return {"cycle_active": False, "cycle_direction": None,
            "terminated_by": None, "warning": False, "warning_zone": None}


def analyze_nci(df_ltf: pd.DataFrame,
                df_htf: pd.DataFrame,
                ltf_window: int = 3,
                htf_window: int = 5) -> dict:
    """
    Pipeline completo NCI Level 0 — orquestra as 4 camadas.

    Ordem de execução:
      1. classify_candles em LTF e HTF
      2. analyze_market_structure em HTF e LTF
      3. detect_pullback a partir do KL do LTF
      4. is_valid_bos se pullback encontrado
      5. detect_range com injecção de tipo quando aplicável
      6. evaluate_key_level_quality
      7. check_market_cycle com zonas do HTF

    Os 4 Factores NCI:
      trend        — LTF em uptrend ou downtrend
      zone         — KL existe E qualidade != "invalid"
      momentum     — pullback detectado
      confirmation — BOS válido
      all_aligned  — todos os 4 True E ciclo activo

    Args:
        df_ltf:     DataFrame OHLC do Lower Time Frame
        df_htf:     DataFrame OHLC do Higher Time Frame
        ltf_window: janela de find_swings para o LTF (default 3)
        htf_window: janela de find_swings para o HTF (default 5)

    Retorna:
        {
          "trend", "key_level", "key_level_quality",
          "pullback", "bos", "range", "market_cycle",
          "htf_trend", "htf_key_level",
          "four_factors": {
            "trend", "zone", "momentum", "confirmation", "all_aligned"
          }
        }
    """
    df_ltf = df_ltf.reset_index(drop=True)
    df_htf = df_htf.reset_index(drop=True)

    # 1. Classify
    df_ltf = classify_candles(df_ltf)
    df_htf = classify_candles(df_htf)

    # 2. Structure
    htf_ms = analyze_market_structure(df_htf, window=htf_window)
    ltf_ms = analyze_market_structure(df_ltf, window=ltf_window)

    # 3. KL and trend
    ltf_kl    = ltf_ms["key_level"]
    ltf_trend = ltf_ms["trend"]
    pb_dir    = ("up"   if ltf_trend == "uptrend"
                 else "down" if ltf_trend == "downtrend"
                 else None)

    # 4. Pullback
    pullback = None
    if ltf_kl is not None and pb_dir is not None:
        pullback = detect_pullback(df_ltf, pb_dir, ltf_kl["index"])

    # 5. BOS + range type injection
    bos               = None
    range_type_inject = None
    if pullback is not None:
        bos = is_valid_bos(
            df_ltf,
            key_level_price=ltf_kl["price"],
            key_level_index=ltf_kl["index"],
            direction=pb_dir,
        )
        if bos and bos["type"] == "fake_breakout":
            range_type_inject = "fake_breakout"
    else:
        range_type_inject = "invalid_pullback"

    # 6. Range
    range_start  = ltf_kl["index"] if ltf_kl is not None else df_ltf.index[0]
    range_result = detect_range(df_ltf, range_start, range_type=range_type_inject)

    # 7. KL quality
    pb_start   = pullback["candles"][0]  if pullback else 0
    pb_end     = pullback["candles"][-1] if pullback else 0
    kl_anchor  = ltf_kl if ltf_kl is not None else {"price": 0.0, "index": 0, "type": None}
    kl_quality = evaluate_key_level_quality(kl_anchor, range_result, pb_start, pb_end)

    # 8. HTF zones + market cycle
    htf_kl    = htf_ms["key_level"]
    htf_zones = {
        "down_key_level": htf_kl["price"] if (htf_kl and htf_ms["trend"] == "downtrend") else None,
        "up_key_level":   htf_kl["price"] if (htf_kl and htf_ms["trend"] == "uptrend")   else None,
        "poi_zone_high":  None,
        "poi_zone_low":   None,
        "recent_high":    float(max(htf_ms["swing_highs"])) if htf_ms["swing_highs"] else None,
        "recent_low":     float(min(htf_ms["swing_lows"]))  if htf_ms["swing_lows"]  else None,
    }
    market_cycle = check_market_cycle(
        ltf_current_price=float(df_ltf["close"].iloc[-1]),
        ltf_trend=ltf_trend,
        htf_zones=htf_zones,
        ltf_key_level_price=float(ltf_kl["price"]) if ltf_kl else None,
    )

    # 9. Four factors
    trend_ok    = ltf_trend in ("uptrend", "downtrend")
    zone_ok     = ltf_kl is not None and kl_quality["quality"] != "invalid"
    momentum_ok = pullback is not None
    confirm_ok  = bos is not None and bos.get("valid") is True
    all_aligned = trend_ok and zone_ok and momentum_ok and confirm_ok and market_cycle["cycle_active"]

    return {
        "trend":             ltf_trend,
        "key_level":         ltf_kl,
        "key_level_quality": kl_quality,
        "pullback":          pullback,
        "bos":               bos,
        "range":             range_result,
        "market_cycle":      market_cycle,
        "htf_trend":         htf_ms["trend"],
        "htf_key_level":     htf_kl,
        "four_factors": {
            "trend":        trend_ok,
            "zone":         zone_ok,
            "momentum":     momentum_ok,
            "confirmation": confirm_ok,
            "all_aligned":  all_aligned,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Testes
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    SEP = "-" * 62

    print(SEP)
    print("Camada 1 — classify_candle()")
    print(SEP)

    # (open_, high, low, close, tipo_esperado)
    # Nota sobre caso 3: spec diz body >= 50%, mas (100,115,85,113) tem
    # body_pct = 43 %.  O critério decisivo é close_level = 93 % >= 90 %
    # e body_pct = 43 % >= 25 % (floor de exclusão de dojis).
    # Ver docstring de classify_candle para justificação.
    casos = [
        (100,   110,  99,    109,   "marubozu"),          # body=9/11=81.8%
        (110,   111,  99,    100,   "marubozu"),           # down, body=10/12=83%
        (100,   115,  85,    113,   "special_marubozu"),   # body=13/30=43%, cl=93%
        (100,   120,  80,    108,   "pinbar"),              # body=8/40=20%
        (100,   101,  99,    100.1, "doji"),                # body=0.1/2=5%
        (100,   108,  97,    103,   "normal"),              # body=3/11=27%, cl=55%
    ]

    all_pass = True
    for open_, high, low, close, expected in casos:
        r  = classify_candle(open_, high, low, close)
        ok = r["type"] == expected
        if not ok:
            all_pass = False
        mark = "✅" if ok else "❌"
        print(f"  {mark} expected={expected:<18}  got={r['type']:<18} "
              f"body_pct={r['body_pct']:.0%}  total={r['total_length']:.4g}")

    print()
    print(SEP)
    print("is_big_candle()")
    print(SEP)

    big_casos = [
        (20,  [30, 40, 35], True,  "20 >= 50%*40=20"),
        (19,  [30, 40, 35], False, "19 < 20"),
        (10,  [],           False, "lista vazia → False"),
        (100, [150],        True,  "100 >= 75"),
        (74,  [150],        False, "74 < 75"),
    ]
    for tl, maru, expected, label in big_casos:
        got  = is_big_candle(tl, maru)
        mark = "✅" if got == expected else "❌"
        print(f"  {mark} {label:<28}  got={got}")

    print()
    print(SEP)
    print("is_small_candle()")
    print(SEP)

    small_casos = [
        (3,  10,  True,  "3 <= 30%*10=3"),
        (4,  10,  False, "4 > 3"),
        (0,  10,  True,  "0 <= 3"),
        (3,  0,   False, "prev=0 → False"),
        (2,  7,   True,  "2 <= 30%*7=2.1"),
    ]
    for tl, prev, expected, label in small_casos:
        got  = is_small_candle(tl, prev)
        mark = "✅" if got == expected else "❌"
        print(f"  {mark} {label:<28}  got={got}")

    print()
    print(SEP)
    print("classify_candles() — série com contexto")
    print(SEP)

    data = {
        "open":  [100, 100, 100, 100, 100, 100],
        "high":  [110,  115, 120, 101, 108,  111],
        "low":   [ 99,   85,  80,  99,  97,   99],
        "close": [109,  113, 108, 100.1, 103, 100],
    }
    df_test = pd.DataFrame(data)
    df_out  = classify_candles(df_test)
    print(df_out[["open", "high", "low", "close",
                  "candle_type", "direction", "body_pct"]].to_string(index=True))

    print()
    print(SEP)
    print("Camada 2 — Market Structure")
    print(SEP)

    # Série sintética de 25 candles (high=low=close para simplicidade)
    # Uptrend: SL@4(92) SH@9(110) HL@14(96)=KL HH@19(120) → uptrend
    closes_up  = [100,98,96,94,92, 95,100,104,108,110,
                  108,105,102,99,96, 100,105,110,115,120,
                  118,116,114,112,110]
    # Downtrend: SH@4(108) SL@9(90) LH@14(104)=KL LL@19(84) → downtrend
    closes_dn  = [100,102,104,106,108, 105,102,98,94,90,
                   92, 95, 98,101,104, 100, 96,92,88,84,
                   86, 88, 90, 92, 94]
    # Range: SH@3(112) SL@9(92) LH@14(111) HL@19(93) → range
    closes_rng = [100,104,108,112,110,107,103,99,95,92,
                   95, 99,103,107,111,108,104,100,96,93,
                   96, 99,102,105,108]

    test_series = [
        ("Uptrend",   closes_up,  "uptrend"),
        ("Downtrend", closes_dn,  "downtrend"),
        ("Range",     closes_rng, "range"),
    ]

    for label, closes, expected_trend in test_series:
        df2 = pd.DataFrame({
            "open":  closes,
            "high":  closes,
            "low":   closes,
            "close": closes,
        })
        ms = analyze_market_structure(df2, window=2)

        trend_ok = ms["trend"] == expected_trend
        kl_ok    = (ms["key_level"] is not None) if expected_trend in ("uptrend", "downtrend") else True
        mark_t   = "✅" if trend_ok else "❌"
        mark_k   = "✅" if kl_ok   else "❌"

        print(f"  {mark_t} trend={ms['trend']:<12} (expected {expected_trend})")
        if ms["key_level"]:
            kl = ms["key_level"]
            print(f"  {mark_k} key_level: idx={kl['index']}  price={kl['price']}  type={kl['type']}")
        else:
            print(f"  {mark_k} key_level: None")
        print(f"     swing_highs={ms['swing_highs']}")
        print(f"     swing_lows ={ms['swing_lows']}")
        if ms["external"] is not None:
            print(f"     external rows: {len(ms['external'])}  internal rows: {len(ms['internal'])}")
        print()

    print()
    print(SEP)
    print("Camada 3 — Pullback & Breakout Standards")
    print(SEP)

    def _mk(rows):
        return classify_candles(pd.DataFrame(rows, columns=["open", "high", "low", "close"]))

    # A: Two Marubozu pullback
    # row0: Maru up tl=11 body=82%
    # row1: Maru up tl=11 body=82%  close1=118>close0=109 ✓  tl1>=70%*tl0 ✓
    df_a = _mk([(100, 110, 99, 109), (109, 119, 108, 118)])
    r_a  = detect_pullback(df_a, "up", 0)
    ok_a = r_a is not None and r_a["pattern"] == "two_marubozu"
    if not ok_a:
        all_pass = False
    print(f"  {'✅' if ok_a else '❌'} A two_marubozu pullback: "
          f"pattern={r_a['pattern'] if r_a else None}  entry={r_a['entry_price'] if r_a else None}")

    # B: Big Maru + Small pullback
    # row0: Maru up tl=16 (context Maru para is_big_candle)
    # row1: Maru up tl=23 body=21 — is_big_candle(23,[16])=True ✓
    # row2: Normal tl=6 — is_small(6,23)=True ✓  low=117>99+11.5=110.5 ✓
    df_b = _mk([(100, 115, 99, 114), (100, 122, 99, 121), (121, 123, 117, 118)])
    r_b  = detect_pullback(df_b, "up", 1)
    ok_b = r_b is not None and r_b["pattern"] == "big_maru_small"
    if not ok_b:
        all_pass = False
    print(f"  {'✅' if ok_b else '❌'} B big_maru_small pullback: "
          f"pattern={r_b['pattern'] if r_b else None}  entry={r_b['entry_price'] if r_b else None}")

    # C: PAC pullback
    # row1: big Maru up (same as B)
    # row2: small (tl=6 ≤6.9 ✓) but low=107 < 110.5 → position FAILS → PAC triggered
    # row3: close=124 > max(high[1]=122, high[2]=113) → PAC confirmed
    df_c = _mk([
        (100, 115,  99, 114),
        (100, 122,  99, 121),
        (110, 113, 107, 108),
        (108, 125, 107, 124),
    ])
    r_c  = detect_pullback(df_c, "up", 1)
    ok_c = r_c is not None and r_c["pattern"] == "pac"
    if not ok_c:
        all_pass = False
    print(f"  {'✅' if ok_c else '❌'} C pac pullback: "
          f"pattern={r_c['pattern'] if r_c else None}  entry={r_c['entry_price'] if r_c else None}")

    # D: Two Marubozu breakout
    # Same candles as A but boi_price=105; close0=109>105 ✓  close1=118>105 ✓
    df_d = _mk([(100, 110, 99, 109), (109, 119, 108, 118)])
    r_d  = detect_breakout(df_d, 105.0, "up", 0)
    ok_d = r_d is not None and r_d["pattern"] == "two_marubozu" and r_d.get("boi_confirmed")
    if not ok_d:
        all_pass = False
    print(f"  {'✅' if ok_d else '❌'} D two_marubozu breakout: "
          f"pattern={r_d['pattern'] if r_d else None}  "
          f"boi_confirmed={r_d.get('boi_confirmed') if r_d else None}")

    # E: Big Maru + Small breakout
    # row1: Maru up body=21; body_above_boi=121-108=13 → 62%>30% ✓
    # row2: small, positioned ✓ (same as B row2)
    df_e = _mk([(100, 115, 99, 114), (100, 122, 99, 121), (121, 123, 117, 118)])
    r_e  = detect_breakout(df_e, 108.0, "up", 1)
    ok_e = r_e is not None and r_e["pattern"] == "big_maru_small" and r_e.get("boi_confirmed")
    if not ok_e:
        all_pass = False
    print(f"  {'✅' if ok_e else '❌'} E big_maru_small breakout: "
          f"pattern={r_e['pattern'] if r_e else None}  "
          f"boi_confirmed={r_e.get('boi_confirmed') if r_e else None}")

    # F: Fake Breakout
    # key_level_index=0; after it: row1 close=106>105 but no valid pattern
    df_f = _mk([(100, 107, 99, 103), (103, 109, 101, 106), (106, 108, 104, 105)])
    r_f  = is_valid_bos(df_f, 105.0, 0, "up")
    ok_f = r_f["type"] == "fake_breakout" and not r_f["valid"]
    if not ok_f:
        all_pass = False
    print(f"  {'✅' if ok_f else '❌'} F fake_breakout: "
          f"type={r_f['type']}  fake_at={r_f['fake_at_index']}")

    print()
    print(SEP)
    print("Camada 4 — Range Detection & KL Quality")
    print(SEP)

    # A: Range by Marubozu
    # row0: Maru up (anchor) anchor_high=120 anchor_low=99
    # rows 1-3: closes 110,115,105 all inside [99,120] ✓
    df_r_a = _mk([
        (100, 120,  99, 119),   # Maru up  body=90.5%
        (119, 121, 108, 110),   # Normal   close=110 ∈ [99,120] ✓
        (110, 117, 108, 115),   # Normal   close=115 ∈ [99,120] ✓
        (115, 116, 103, 105),   # Normal   close=105 ∈ [99,120] ✓
    ])
    r4a  = detect_range(df_r_a, 0)
    ok_4a = r4a["detected"] and r4a["type"] == "marubozu"
    if not ok_4a:
        all_pass = False
    print(f"  {'✅' if ok_4a else '❌'} A range_marubozu: "
          f"detected={r4a['detected']}  type={r4a['type']}  "
          f"inside={r4a['candles_inside']}")

    # B: Low Liquidity Range (Doji anchor)
    # rows 0-9: tl=40 each → avg_10=40 for anchor
    # row 10: tiny Doji tl=0.8 → 0.8 < 30%*40=12 → low_liq=True
    # rows 11-13: closes inside [99.6, 100.4]
    _big  = [(100, 120, 80, 100)] * 10         # tl=40, body=0 → Doji → Normal after ctx
    _doji = [(100, 100.4, 99.6, 100)]          # tl=0.8, body=0 → Doji (stays small)
    _in   = [(100, 100.3, 99.7, 100.1),        # close=100.1 ∈ [99.6,100.4] ✓
             (100.1, 100.2, 99.8, 100.0),      # close=100.0 ✓
             (100,   100.3, 99.7, 100.2)]      # close=100.2 ✓
    df_r_b = _mk(_big + _doji + _in)
    r4b   = detect_range(df_r_b, 10)
    ok_4b = r4b["detected"] and r4b["low_liquidity"]
    if not ok_4b:
        all_pass = False
    print(f"  {'✅' if ok_4b else '❌'} B low_liquidity: "
          f"detected={r4b['detected']}  low_liq={r4b['low_liquidity']}  "
          f"type={r4b['type']}")

    # C: KL invalid — range anchor AFTER pullback end
    _kl_c         = {"price": 100.0, "index": 10, "type": "HL"}
    _range_after  = {"detected": True, "anchor_index": 8,
                     "anchor_price_high": 110.0, "anchor_price_low": 95.0,
                     "type": "marubozu", "low_liquidity": False, "candles_inside": [9, 10]}
    r4c  = evaluate_key_level_quality(_kl_c, _range_after,
                                      pullback_start_idx=5, pullback_end_idx=6)
    ok_4c = r4c["quality"] == "invalid"
    if not ok_4c:
        all_pass = False
    print(f"  {'✅' if ok_4c else '❌'} C kl_invalid: "
          f"quality={r4c['quality']}  ({r4c['reason']})")

    # D: KL weak — range anchor BEFORE pullback start
    _range_before = {"detected": True, "anchor_index": 2,
                     "anchor_price_high": 110.0, "anchor_price_low": 95.0,
                     "type": "marubozu", "low_liquidity": False, "candles_inside": [3, 4]}
    r4d  = evaluate_key_level_quality(_kl_c, _range_before,
                                      pullback_start_idx=5, pullback_end_idx=6)
    ok_4d = r4d["quality"] == "weak"
    if not ok_4d:
        all_pass = False
    print(f"  {'✅' if ok_4d else '❌'} D kl_weak: "
          f"quality={r4d['quality']}  ({r4d['reason']})")

    print()
    print(SEP)
    print("Camada 4 (cont.) — Market Cycle & analyze_nci()")
    print(SEP)

    _htf_z = lambda rh: {
        "down_key_level": None, "up_key_level": None,
        "poi_zone_high": None, "poi_zone_low": None,
        "recent_high": rh, "recent_low": None,
    }

    # A: Ciclo termina — ltf_price atingiu recent_high
    r5a  = check_market_cycle(120.0, "uptrend", _htf_z(120.0))
    ok_5a = not r5a["cycle_active"] and r5a["terminated_by"] == "recent_high"
    if not ok_5a:
        all_pass = False
    print(f"  {'✅' if ok_5a else '❌'} A cycle_terminated: "
          f"active={r5a['cycle_active']}  by={r5a['terminated_by']}")

    # B: Warning activo — faltam 17.5% (3.5/20) < 20% do percurso
    # KL=100, zona=120, price=116.5 → dist_total=20 dist_actual=3.5
    r5b  = check_market_cycle(116.5, "uptrend", _htf_z(120.0), ltf_key_level_price=100.0)
    ok_5b = r5b["cycle_active"] and r5b["warning"] and r5b["warning_zone"] == "recent_high"
    if not ok_5b:
        all_pass = False
    print(f"  {'✅' if ok_5b else '❌'} B warning_active: "
          f"active={r5b['cycle_active']}  warning={r5b['warning']}  "
          f"zone={r5b['warning_zone']}")

    # C: Ciclo activo, sem warning — faltam 75% (15/20) > 20%
    # KL=100, zona=120, price=105 → dist_total=20 dist_actual=15
    r5c  = check_market_cycle(105.0, "uptrend", _htf_z(120.0), ltf_key_level_price=100.0)
    ok_5c = r5c["cycle_active"] and not r5c["warning"]
    if not ok_5c:
        all_pass = False
    print(f"  {'✅' if ok_5c else '❌'} C cycle_active_no_warning: "
          f"active={r5c['cycle_active']}  warning={r5c['warning']}")

    # D: analyze_nci() com 4 factores alinhados
    # LTF (21 rows, window=3):
    #   pos3=SL(91) pos7=SH(109) pos11=HL=KL(95) pos15=HH(113)
    #   pos19-20: Maru up → Two Marubozu pullback + BOS above KL=95
    _ltf_rows = [
        (100,100,100,100),(97,97,97,97),(94,94,94,94),
        (91, 91, 91, 91),                   # pos  3: SL
        (95, 95, 95, 95),(100,100,100,100),(105,105,105,105),
        (109,109,109,109),                  # pos  7: SH
        (105,105,105,105),(101,101,101,101),(98,98,98,98),
        (95, 95, 95, 95),                   # pos 11: HL=KL
        (99, 99, 99, 99),(104,104,104,104),(109,109,109,109),
        (113,113,113,113),                  # pos 15: HH
        (110,110,110,110),(107,107,107,107),(104,104,104,104),
        (104,114,103,113),                  # pos 19: Maru up (tl=11 body=82%)
        (113,123,112,122),                  # pos 20: Maru up (tl=11 body=82%) close=122
    ]
    # HTF (29 rows, window=5):
    #   pos5=SL(85) pos11=SH(115) pos17=HL=KL(87) pos23=HH(200)
    #   recent_high=200 >> LTF price=122 → cycle active
    _htf_rows = [
        (100,100,100,100),(97,97,97,97),(94,94,94,94),(91,91,91,91),(88,88,88,88),
        (85, 85, 85, 85),                   # pos  5: SL
        (90,90,90,90),(95,95,95,95),(100,100,100,100),(105,105,105,105),(110,110,110,110),
        (115,115,115,115),                  # pos 11: SH
        (110,110,110,110),(105,105,105,105),(100,100,100,100),(95,95,95,95),(90,90,90,90),
        (87, 87, 87, 87),                   # pos 17: HL=KL
        (92,92,92,92),(97,97,97,97),(102,102,102,102),(107,107,107,107),(112,112,112,112),
        (200,200,200,200),                  # pos 23: HH (recent_high=200)
        (180,180,180,180),(160,160,160,160),(140,140,140,140),(120,120,120,120),(100,100,100,100),
    ]
    _cols = ["open","high","low","close"]
    df_ltf_d = pd.DataFrame(_ltf_rows, columns=_cols)
    df_htf_d = pd.DataFrame(_htf_rows, columns=_cols)

    r5d  = analyze_nci(df_ltf_d, df_htf_d, ltf_window=3, htf_window=5)
    ok_5d = r5d["four_factors"]["all_aligned"]
    if not ok_5d:
        all_pass = False
    print(f"  {'✅' if ok_5d else '❌'} D analyze_nci all_aligned={ok_5d}")
    print(f"     trend={r5d['trend']}  htf_trend={r5d['htf_trend']}")
    kl5d = r5d['key_level']
    print(f"     key_level: idx={kl5d['index']} price={kl5d['price']} "
          f"quality={r5d['key_level_quality']['quality']}")
    pb5d = r5d['pullback']
    print(f"     pullback: pattern={pb5d['pattern']} candles={pb5d['candles']}")
    b5d  = r5d['bos']
    print(f"     bos: valid={b5d['valid']} type={b5d['type']}")
    mc5d = r5d['market_cycle']
    print(f"     market_cycle: active={mc5d['cycle_active']} warning={mc5d['warning']}")
    ff5d = r5d['four_factors']
    print(f"     four_factors: trend={ff5d['trend']} zone={ff5d['zone']} "
          f"momentum={ff5d['momentum']} confirmation={ff5d['confirmation']} "
          f"all_aligned={ff5d['all_aligned']}")

    print()
    print(SEP)
    print("Resultado global:", "✅ Todos os casos OK" if all_pass else "❌ Algum caso falhou")
    print(SEP)
