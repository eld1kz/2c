import copy
import json

from app.engine.categorize import ClassifyItem, ClassifyResult


class FakeClassifier:
    """Stands in for the LLM: answers one category/confidence for every item and records calls."""

    def __init__(self, category: str = "software", confidence: float = 0.92) -> None:
        self.category = category
        self.confidence = confidence
        self.calls: list[list[ClassifyItem]] = []

    def classify(self, items: list[ClassifyItem]) -> list[ClassifyResult]:
        self.calls.append(items)
        return [ClassifyResult(i.index, self.category, self.confidence) for i in items]

    @property
    def descriptions(self) -> list[str]:
        return [i.description for call in self.calls for i in call]


class ScriptedModel:
    """Stands in for Claude in the agent loop: replays scripted replies and records every request.

    Each step is a list of blocks, or a function of the message history returning one (to use ids
    from earlier tool results), or an exception to raise. A block is a str (text) or a
    ("tool_name", {input}) tuple (a tool call). When the script runs out it answers "Okay."
    """

    def __init__(self, *steps: object, usage: object = None, model: str = "claude-sonnet-5-5") -> None:
        self.steps = list(steps)
        self.requests: list[dict] = []
        self._ids = 0
        self.usage = usage  # a runner.Usage billed for every call (default: none)
        self.model = model
        self.timeouts: list[float] = []  # the `timeout` each call was given

    def stream(self, *, system: str, tools: list[dict], messages: list[dict], tool_choice: dict,  # noqa: ANN201
               timeout: float):
        from app.agent.runner import Final, TextDelta

        self.timeouts.append(timeout)
        self.requests.append(copy.deepcopy({"system": system, "tools": [t["name"] for t in tools],
                                            "messages": messages, "tool_choice": tool_choice}))
        step = self.steps.pop(0) if self.steps else ["Okay."]
        if isinstance(step, Exception):
            raise step
        blocks = []
        for item in step(messages) if callable(step) else step:
            if isinstance(item, str):
                blocks.append({"type": "text", "text": item})
                yield TextDelta(item)
            else:
                self._ids += 1
                blocks.append({"type": "tool_use", "id": f"toolu_{self._ids:03d}", "name": item[0], "input": item[1]})
        stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
        yield Final(blocks, stop, self.usage) if self.usage is not None else Final(blocks, stop)

    @property
    def sent(self) -> str:
        """Everything the server ever sent to the model, as one string (for leak checks)."""
        return json.dumps(self.requests, ensure_ascii=False)


def tool_result(messages: list[dict], tool_name: str) -> dict:
    """The latest parsed result of `tool_name` in a message history."""
    names = {b["id"]: b["name"] for m in messages if m["role"] == "assistant" for b in m["content"]
             if b.get("type") == "tool_use"}
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "tool_result" and names.get(b["tool_use_id"]) == tool_name:
                    return json.loads(b["content"])
    raise LookupError(tool_name)
