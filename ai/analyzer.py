import os
from openai import OpenAI
from backtester.engine import BacktestResult
from strategy.models import Strategy


def _build_prompt(
    result: BacktestResult,
    strategy: Strategy,
    asset: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    initial_capital: float,
) -> str:
    indicators_str = ", ".join(
        f"{i.name}({', '.join(f'{k}={v}' for k, v in i.params.items())})"
        for i in strategy.indicators
    )

    def fmt_rule(rule):
        if rule is None or not rule.conditions:
            return "—"
        parts = [f"{c.indicator} {c.operator} {c.value}" for c in rule.conditions]
        return f" {rule.logic} ".join(parts)

    entry_str = fmt_rule(strategy.entry_rule)
    exit_str  = fmt_rule(strategy.exit_rule)
    tp_str    = f"{strategy.take_profit_pct}%" if strategy.take_profit_pct else "нет"
    sl_str    = f"{strategy.stop_loss_pct}%"   if strategy.stop_loss_pct   else "нет"

    wins   = [t for t in result.trades if t["pnl_pct"] > 0]
    losses = [t for t in result.trades if t["pnl_pct"] <= 0]
    reasons = {}
    for t in result.trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    reasons_str = ", ".join(f"{r}: {n}" for r, n in reasons.items())

    return f"""Ты — опытный трейдер и аналитик алгоритмических торговых стратегий. \
Проанализируй результаты бэктеста и дай конкретную, практическую обратную связь.

## Параметры стратегии

- **Актив:** {asset}
- **Таймфрейм:** {timeframe}
- **Период бэктеста:** {start_date} — {end_date}
- **Начальный капитал:** ${initial_capital:,.0f}
- **Комиссия:** учтена в расчётах
- **Индикаторы:** {indicators_str}
- **Условие входа ({strategy.entry_rule.logic}):** {entry_str}
- **Условие выхода:** {exit_str}
- **Тейк-профит:** {tp_str}
- **Стоп-лосс:** {sl_str}

## Результаты бэктеста

| Метрика | Значение |
|---------|----------|
| Доходность | {result.total_return_pct:+.2f}% |
| Количество сделок | {result.num_trades} |
| Прибыльных сделок | {result.win_rate_pct:.1f}% ({len(wins)} из {result.num_trades}) |
| Убыточных сделок | {100 - result.win_rate_pct:.1f}% ({len(losses)} из {result.num_trades}) |
| Максимальная просадка | {result.max_drawdown_pct:.2f}% |
| Sharpe Ratio | {result.sharpe_ratio:.3f} |
| Средний выигрыш | {result.avg_win_pct:+.2f}% |
| Средний проигрыш | {result.avg_loss_pct:+.2f}% |
| Причины выхода | {reasons_str} |

## Задача

Дай ответ **строго** в следующем формате (используй именно эти заголовки):

**Краткая оценка**
2–3 предложения: общее качество стратегии, подходит ли она для реальной торговли.

**Слабые места**
- [слабое место 1 — конкретно, не абстрактно]
- [слабое место 2]
- [слабое место 3 если есть]

**Рекомендации**
1. [конкретная рекомендация с объяснением почему она улучшит результат]
2. [рекомендация]
3. [рекомендация]

**Риск переобучения**
Оцени, насколько вероятно что стратегия переобучена под исторические данные \
и что конкретно нужно проверить перед реальной торговлей.

Отвечай на русском языке. Будь конкретным — избегай общих фраз.
"""


def analyze_strategy(
    result: BacktestResult,
    strategy: Strategy,
    asset: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    initial_capital: float,
) -> str:
    """
    Send backtest results to Claude via polza.ai proxy and return AI commentary.
    Raises on API errors so the caller can handle them gracefully.
    """
    # Try st.secrets first (Streamlit Cloud), fall back to os.getenv (local .env)
    try:
        import streamlit as st
        api_key  = st.secrets.get("CLAUDE_API_KEY")  or os.getenv("CLAUDE_API_KEY")
        base_url = st.secrets.get("CLAUDE_BASE_URL") or os.getenv("CLAUDE_BASE_URL", "https://polza.ai/api/v1")
        model    = st.secrets.get("CLAUDE_MODEL")    or os.getenv("CLAUDE_MODEL",    "anthropic/claude-sonnet-4.6")
    except Exception:
        api_key  = os.getenv("CLAUDE_API_KEY")
        base_url = os.getenv("CLAUDE_BASE_URL", "https://polza.ai/api/v1")
        model    = os.getenv("CLAUDE_MODEL",    "anthropic/claude-sonnet-4.6")

    if not api_key:
        raise ValueError("CLAUDE_API_KEY не найден. Добавьте его в .env (локально) или в Secrets (Streamlit Cloud).")

    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_prompt(
        result, strategy, asset, timeframe, start_date, end_date, initial_capital
    )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        temperature=0.4,
    )

    return response.choices[0].message.content.strip()
