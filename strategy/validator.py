from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from strategy.models import IndicatorConfig, Rule

CANDLES_PER_DAY: dict[str, float] = {
    "1m":  1440,
    "5m":   288,
    "15m":   96,
    "30m":   48,
    "1h":    24,
    "4h":     6,
    "1d":     1,
    "1w":  1 / 7,
}


@dataclass
class ValidationIssue:
    level: str   # "error" | "warning"
    message: str


def _min_candles_for_indicator(name: str, params: dict) -> int:
    """Minimum candles needed before an indicator produces non-NaN values."""
    if name == "RSI":
        return params["period"] + 1
    if name == "MACD":
        return params["slow"] + params["signal"]
    if name in ("EMA", "SMA", "BB", "VolumeSMA", "CCI"):
        return params["period"]
    if name == "Stochastic":
        return params["k"] + params["d"]
    if name == "ATR":
        return params["period"] + 1
    if name == "Supertrend":
        return params["period"] * 3  # needs ATR warmup
    return 1


def _indicator_columns(name: str, params: dict) -> list[str]:
    """Column names that will be added to df for a given indicator."""
    p = params
    if name == "RSI":
        return [f"RSI_{p['period']}"]
    if name == "MACD":
        return [f"MACD_{p['fast']}_{p['slow']}_{p['signal']}",
                f"MACDs_{p['fast']}_{p['slow']}_{p['signal']}",
                f"MACDh_{p['fast']}_{p['slow']}_{p['signal']}"]
    if name == "EMA":
        return [f"EMA_{p['period']}"]
    if name == "SMA":
        return [f"SMA_{p['period']}"]
    if name == "BB":
        s = str(p["std"]).replace(".", "_")
        return [f"BB_upper_{p['period']}_{s}",
                f"BB_mid_{p['period']}_{s}",
                f"BB_lower_{p['period']}_{s}"]
    if name == "Stochastic":
        return [f"STOCHk_{p['k']}_{p['d']}_3", f"STOCHd_{p['k']}_{p['d']}_3"]
    if name == "ATR":
        return [f"ATR_{p['period']}"]
    if name == "VolumeSMA":
        return [f"VolSMA_{p['period']}"]
    if name == "CCI":
        return [f"CCI_{p['period']}"]
    if name == "Supertrend":
        m = str(p["multiplier"]).replace(".", "_")
        return [f"ST_{p['period']}_{m}", f"ST_dir_{p['period']}_{m}"]
    return []


def estimate_candle_count(start_date: str, end_date: str, timeframe: str) -> int:
    days = (datetime.strptime(end_date, "%Y-%m-%d")
            - datetime.strptime(start_date, "%Y-%m-%d")).days
    rate = CANDLES_PER_DAY.get(timeframe, 24)
    return max(0, int(days * rate))


def validate(
    indicators: list[IndicatorConfig],
    entry_rule: Rule,
    exit_rule: Rule | None,
    start_date: str,
    end_date: str,
    timeframe: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # 1. Date range
    try:
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date,   "%Y-%m-%d")
        if e <= s:
            issues.append(ValidationIssue("error", "Дата окончания должна быть позже даты начала."))
            return issues  # no point continuing
        if (e - s).days < 7:
            issues.append(ValidationIssue("warning", "Период меньше 7 дней — результаты бэктеста будут ненадёжными."))
    except ValueError as exc:
        issues.append(ValidationIssue("error", f"Некорректный формат даты: {exc}"))
        return issues

    # 2. Estimate candle count vs required warmup
    estimated = estimate_candle_count(start_date, end_date, timeframe)
    if estimated < 50:
        issues.append(ValidationIssue(
            "error",
            f"Слишком мало свечей (~{estimated}) для выбранного периода и таймфрейма. "
            "Расширьте диапазон дат или выберите меньший таймфрейм."
        ))

    max_required = 0
    bottleneck = ""
    for cfg in indicators:
        needed = _min_candles_for_indicator(cfg.name, cfg.params)
        if needed > max_required:
            max_required = needed
            params_str = ", ".join(f"{k}={v}" for k, v in cfg.params.items())
            bottleneck = f"{cfg.name}({params_str})"

    if max_required > 0 and estimated < max_required * 3:
        issues.append(ValidationIssue(
            "warning",
            f"{bottleneck} требует минимум {max_required} свечей для прогрева, "
            f"а в выбранном периоде ожидается ~{estimated}. "
            "Многие сигналы в начале периода будут пропущены — рассмотрите более широкий диапазон дат."
        ))

    # 3. Check condition columns exist in configured indicators
    available = {"open", "high", "low", "close", "volume"}
    for cfg in indicators:
        available.update(_indicator_columns(cfg.name, cfg.params))

    all_rules = [entry_rule] + ([exit_rule] if exit_rule else [])
    for rule in all_rules:
        for cond in rule.conditions:
            if cond.indicator not in available:
                issues.append(ValidationIssue(
                    "error",
                    f"Колонка «{cond.indicator}» не найдена среди добавленных индикаторов. "
                    f"Проверьте параметры индикатора — возможно, период не совпадает."
                ))
            if isinstance(cond.value, str) and cond.value not in available:
                issues.append(ValidationIssue(
                    "error",
                    f"Колонка «{cond.value}» (правая часть условия) не найдена среди добавленных индикаторов."
                ))

    # 4. No exit defined at all
    has_exit_signal = exit_rule and exit_rule.conditions
    has_tp_sl = False  # caller checks TP/SL — pass via separate flag if needed
    if not has_exit_signal:
        issues.append(ValidationIssue(
            "warning",
            "Не задано сигнальное условие выхода. "
            "Позиции будут закрываться только по TP/SL или принудительно в конце периода."
        ))

    return issues
