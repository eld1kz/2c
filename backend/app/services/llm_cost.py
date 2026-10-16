"""LLM token prices and cost in integer micro-dollars (µUSD), never floats.

Prices are USD per million tokens (Anthropic first-party list prices). Cache reads and writes have
their own rates; a 5-minute cache write costs 1.25× input. An unknown model is priced as the most
expensive one listed, so a budget never under-counts.
"""

from dataclasses import dataclass

MICRO = 1_000_000  # µUSD per USD, and tokens per MTok


@dataclass(frozen=True)
class Price:
    input: int  # µUSD per million tokens
    output: int
    cache_read: int
    cache_write: int


def _usd(input_: str, output: str, cache_read: str, cache_write: str) -> Price:
    def micro(usd: str) -> int:
        whole, _, frac = usd.partition(".")
        return int(whole) * MICRO + int((frac + "000000")[:6])
    return Price(micro(input_), micro(output), micro(cache_read), micro(cache_write))


PRICES: dict[str, Price] = {
    "claude-fable-5-1": _usd("10", "50", "0.25", "12.50"),
    "claude-opus-5-5": _usd("4", "20", "0.20", "5"),
    "claude-sonnet-5-5": _usd("2", "10", "0.20", "2.50"),
    "claude-haiku-5-5": _usd("0.10", "0.50", "0.01", "0.125"),  # prompts up to 100K tokens
}
FALLBACK = max(PRICES.values(), key=lambda p: p.output)


def cost_microusd(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
                  cache_write_tokens: int = 0) -> int:
    price = PRICES.get(model, FALLBACK)
    total = (input_tokens * price.input + output_tokens * price.output + cache_read_tokens * price.cache_read
             + cache_write_tokens * price.cache_write)
    return -(-total // MICRO)  # round up


def usd(microusd: int) -> str:
    return f"${microusd // MICRO}.{microusd % MICRO:06d}"[:-2]  # $0.1234
