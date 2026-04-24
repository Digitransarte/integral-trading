"""
Integral Trading — Especialista Episodic Pivot
================================================
Especialista com conhecimento profundo do método EP do Pradeep Bonde.
Baseado nas fontes primárias: Stockbee blog, transcrições de conferências,
e experiência acumulada dos backtests.
"""

from engine.specialist import BaseSpecialist


class EPSpecialist(BaseSpecialist):

    name          = "Episodic Pivot"
    strategy_name = "ep"

    system_prompt = """
És o especialista em Episodic Pivots (EP) do sistema Integral Trading.

## A tua identidade

O teu conhecimento vem directamente das fontes primárias do Pradeep Bonde 
(Stockbee) — o criador do método EP — complementado pela experiência real 
dos backtests e forward tests feitos neste sistema.

Tens dois modos de operação que combinas naturalmente:

**Modo Professor:** Explicas o método EP em profundidade. Quando alguém tem 
dúvidas sobre o método, explicas os conceitos com clareza, usas exemplos reais, 
e ajudas a desenvolver o entendimento da estratégia.

**Modo Analista:** Quando vês resultados de backtests ou trades reais, analisas 
com rigor o que está a funcionar e o que não está. Sugeres ajustes específicos 
e mensuráveis.

## A tua filosofia

O EP baseia-se no fenómeno PEAD (Post Earnings Announcement Drift), documentado 
cientificamente por Ball e Brown em 1968: stocks no decil superior de surpresa 
de earnings continuam a subir nas semanas seguintes.

O princípio central: quando uma empresa surpreende o mercado com um catalisador 
INESPERADO e MATERIAL, o mercado demora semanas a fazer o repricing completo. 
Esse drift é onde está o dinheiro.

O conceito de "Neglect" é fundamental: as melhores oportunidades EP são em 
stocks que estavam fora do radar — sem cobertura de analistas, com float baixo, 
negligenciadas pelo mercado. O efeito surpresa é máximo.

## Tom e estilo

- Directo e prático — foco em acção e implementação
- Usa exemplos concretos quando possível
- Quando não tens certeza, diz-o claramente
- Responde em português europeu
- Mantém respostas focadas — sem floreados desnecessários
- Quando analisas trades, sê honesto sobre o que falhou
"""

    knowledge = {

        "fundamento_teorico": {
            "base": "PEAD — Post Earnings Announcement Drift (Ball & Brown, 1968)",
            "principio": "Stocks com surpresa positiva de earnings continuam a valorizar nas semanas seguintes",
            "dois_tipos_oportunidade": [
                "Movimento imediato e grande — trade de curto prazo no dia ou dias seguintes",
                "Rally que começa no dia do earnings e continua 3-4 trimestres"
            ],
            "conceito_neglect": "Stock estava fora do radar antes do catalisador — amplifica o efeito surpresa e o drift"
        },

        "criterios_scan_originais": {
            "variacao_diaria_pct":    "≥ 8%",
            "volume_ratio_media100":  "≥ 300% (3x) da média de 100 dias",
            "volume_minimo_absoluto": "≥ 300.000 acções",
            "preco_minimo":           "> $1",
            "formula_telechart":      "((C-C1)>=5 AND V>10000 AND C>=62.50 AND V>V1) OR (((100*(C-C1)/C1)>=8 AND V>3000 AND (100*V/AVGV100)>=300) AND C>1)"
        },

        "criterios_qualidade_float": {
            "ideal":       "Float < 25 milhões — os melhores movimentos",
            "muito_bom":   "Float < 10 milhões — movimentos explosivos possíveis",
            "aceitavel":   "Float 25-100 milhões",
            "evitar":      "Float > 100 milhões — tendência para pullbacks",
            "nao_usar":    "Float > 500 milhões (excepto perto de mínimos históricos)"
        },

        "criterios_qualidade_volume": {
            "ideal":    "Volume no dia do EP = 10x ou mais da média — sinal de movimento grande (100%+ em 1-2 meses)",
            "muito_bom": "Volume = máximo histórico ou máximo de vários anos",
            "minimo":   "3x a média de 100 dias"
        },

        "tipos_catalisadores_22": [
            "Earnings Growth 100%+",
            "Earnings 40%+",
            "Earnings beats by wide margin",
            "Earnings Other",
            "Sales 100%+ sem earnings",
            "IPO Breakout",
            "Retail",
            "Top Sector",
            "New order/contract",
            "Buyout/merger",
            "New product launch",
            "Regulatory Changes",
            "Drug Approval",
            "Drug/marketing Tie Up",
            "Natural disaster/war/disease",
            "Shortages",
            "Rate Increase",
            "Media Mention",
            "Analyst upgrade/downgrade",
            "Declares Dividend",
            "Financial Engineering",
            "Junk of the bottom rally"
        ],

        "entrada": {
            "timing":    "Comprar imediatamente — pré-mercado ou abertura. Os melhores EPs foram comprados em pré-mercado.",
            "regra":     "Se é um bom EP, não esperar — entrar imediatamente",
            "variante_delayed": "Esperar consolidação ordeira após o gap, sem quebras de 4%+ durante o pullback"
        },

        "stop_loss": {
            "regra":     "Mínima dos 2 dias anteriores à entrada",
            "filosofia": "Stop apertado — se o EP é real o preço não deve regressar à mínima dos 2 dias anteriores"
        },

        "saida": {
            "metodo":    "4 partes, target de lucro 20%+, trailing stop",
            "regra":     "Sem price targets fixos — saídas baseadas em trailing stops",
            "horizonte": "Poucas semanas a meses dependendo do momentum"
        },

        "variante_9_million_ep": {
            "descricao":   "Volume surge > 9 milhões numa sessão — evolução moderna do EP clássico",
            "vantagem":    "Mais frequente que EP clássico — 100-200 trades/ano vs 5-10 do EP puro",
            "sugar_babies": "Stocks com EPs de 9M recorrentes — core list de swing trades de 40-50% em 3-5 dias"
        },

        "analise_qualitativa_catalisador": {
            "perguntas_chave": [
                "É a primeira grande aceleração de earnings?",
                "O que causou a aceleração? É pontual ou persistente?",
                "Representa mudança estrutural na indústria ou posição competitiva?",
                "A surpresa já está reflectida no preço actual?",
                "Volume muito elevado = movimento tem 'pernas'"
            ],
            "earnings_sem_cobertura": "Procurar aceleração 100%+ YoY e quarter-over-quarter — melhor oportunidade",
            "earnings_com_cobertura": "Surpresas genuínas são raras — expectativas bem geridas — EPs tendem a ter pullbacks"
        },

        "processo_diario": {
            "pre_mercado": [
                "Correr IB scanner: volume > 50k e subida >= 2%",
                "Analisar movers after-hours: subida > 4% em 50k volume",
                "Verificar se há ação com neglect + game changing earnings"
            ],
            "durante_dia": [
                "Correr EP scan c/c1 > 1.04 e v > 3*avgv50 várias vezes",
                "Verificar neglect + game changing earnings"
            ],
            "ferramentas": [
                "MarketSmith (earnings, float, fund holdings)",
                "TheFlyOnTheWall (notícias)",
                "IB scanner (top % gainers, volume > 50k)",
                "Trade Ideas (biggest gainers + most upside momentum)"
            ]
        },

        "o_que_funciona_no_nosso_sistema": {
            "sectores_positivos": [
                "Small Cap Growth (win rate ~57%, PF ~2.0)",
                "Space & Defense (win rate ~53%, PF ~1.9)",
                "AI & Tech (win rate ~36%, PF ~1.5)",
                "Mid Cap Momentum (win rate ~50%, PF ~1.8)",
                "Healthcare Devices (win rate ~64%, PF ~1.6)"
            ],
            "sectores_negativos": [
                "Biotech — gaps frequentemente negativos (FDA rejections, trial failures) — win rate 24%",
                "Crypto/Fintech — correlação com BTC, não com fundamentais — win rate 29%",
                "Clean Energy — correlação macro/petróleo — win rate 25%"
            ],
            "nota_biotech": "O sistema EP puro não distingue gap positivo de gap negativo — biotech requer análise qualitativa do catalisador obrigatória"
        },

        "criterios_actuais_sistema": {
            "min_gap_pct":      "5% (Pradeep usa 8% — podemos subir)",
            "min_volume_ratio": "2.5x (Pradeep usa 3x da média de 100 dias)",
            "min_price":        "$5",
            "min_score":        "60/100",
            "janela_entrada":   "PRIME (0-5 dias), OPEN (6-10 dias), LATE (>10 dias)",
            "stop":             "8% abaixo da entrada (Pradeep usa mínima dos 2 dias anteriores — mais preciso)",
            "target_1":         "15% acima da entrada",
            "hold_max":         "20 dias"
        }
    }
