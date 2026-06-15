from dataclasses import dataclass, field

# Input price, output price — USD per 1M tokens.
# OpenAI prices are approximate and may be outdated; verify at platform.openai.com/pricing.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-haiku-4-5":  (1.00,   5.00),
    "claude-sonnet-4-6": (3.00,  15.00),
    "claude-opus-4-8":   (5.00,  25.00),
    # OpenAI
    "gpt-4o-mini":       (0.15,   0.60),
    "gpt-4o":            (2.50,  10.00),
    "o3-mini":           (1.10,   4.40),
    "o3":               (10.00,  40.00),
}

# Models whose pricing is unknown — cost will show as $0.00 with a warning.
_UNKNOWN_PRICE_WARNING = (
    "Pricing not available for model {model!r}. "
    "Cost shown as $0.00 — verify at your provider's pricing page."
)


@dataclass
class CostTracker:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    unknown_models: set = field(default_factory=set, repr=False)
    _calls: list[dict] = field(default_factory=list, repr=False)

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        prices = MODEL_PRICES.get(model)
        if prices is None:
            self.unknown_models.add(model)
            cost = 0.0
        else:
            cost = (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000

        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost
        self._calls.append({"model": model, "input": input_tokens, "output": output_tokens, "cost": cost})

    def summary(self) -> dict:
        return {
            "input_tokens":    self.input_tokens,
            "output_tokens":   self.output_tokens,
            "cost_usd":        round(self.cost_usd, 6),
            "calls":           len(self._calls),
            "unknown_models":  list(self.unknown_models),
        }
