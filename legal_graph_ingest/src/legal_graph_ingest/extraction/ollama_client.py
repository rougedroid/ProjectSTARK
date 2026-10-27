"""Stage 4: structured extraction with Ollama. The LLM only *proposes*; Python validates."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, Protocol, TypeVar

from pydantic import BaseModel, Field

from ..config import Settings
from ..models.proposition import ExtractionResult
from ..validation.schema import ValidationFailure
from .context import ExtractionContext

log = logging.getLogger(__name__)
T = TypeVar("T")


class ExtractionFailure(RuntimeError):
    """All retries exhausted. Carries the last raw response so it can be quarantined."""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


class ChatBackend(Protocol):
    def chat(self, *, model: str, messages: list[dict], format: Any, options: dict) -> Any: ...


def default_backend(settings: Settings) -> ChatBackend:
    import ollama

    return ollama.Client(host=settings.ollama_base_url, timeout=settings.ollama_timeout)


def _content(response: Any) -> str:
    try:
        return response["message"]["content"]
    except (KeyError, TypeError):
        return response.message.content


EXTRACTION_SYSTEM_PROMPT = """You extract legal propositions from contract text.

Rules:
1. Extract only what the CLAUSE TEXT states. Never add facts, interpretations or legal conclusions.
2. Every proposition needs `source_quote`: an exact, verbatim, contiguous copy from the CLAUSE TEXT
   (same wording, same punctuation). Do not paraphrase inside source_quote.
3. `normalized_text` is a clear restatement of the proposition in one sentence.
4. modality is one of: obligation, prohibition, permission, entitlement, exception, condition,
   definition, representation, statement. Capture negation in `polarity` (positive|negative).
   Put conditions, exceptions and time limits in `conditions`, `exceptions`, `temporal_scope`.
5. If a statement points back to something earlier ("the foregoing obligation", "such payment", "it",
   "that party"), do NOT invent a new subject. Keep the wording as it appears and add an entry to
   `references` with surface_text and kind (pronoun | anaphoric_phrase | defined_term | cross_reference).
   Put plausible antecedents in `candidate_ids`: ids from EARLIER PROPOSITIONS, or "local:<local_id>"
   for another proposition you output in this same response. If several are plausible, list them all.
   If none is plausible, leave candidate_ids empty. Never force a link.
6. local_id values (p1, p2, ...) must be unique within your response.
7. If the clause contains no propositions (e.g. a heading), return {"propositions": []}.
8. Respond with JSON only, matching the provided schema."""


class OllamaExtractor:
    def __init__(self, settings: Settings, backend: Optional[ChatBackend] = None):
        settings.require_model()
        self.settings = settings
        self.backend = backend or default_backend(settings)
        self.schema = ExtractionResult.model_json_schema()

    def extract(self, ctx: ExtractionContext, validate: Callable[[str], T]) -> T:
        """Call the model, validate with `validate(raw)`, retry with feedback on failure."""
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": ctx.render()},
        ]
        last_raw, last_err = "", "no attempt made"
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                resp = self.backend.chat(
                    model=self.settings.ollama_model,
                    messages=messages,
                    format=self.schema,
                    options={"temperature": 0},
                )
                last_raw = _content(resp)
            except Exception as exc:  # network/model errors are retried too
                last_err = f"ollama call failed: {exc}"
                log.warning("attempt %d/%d: %s", attempt, self.settings.max_retries, last_err)
                continue
            try:
                return validate(last_raw)
            except ValidationFailure as exc:
                last_err = exc.message
                log.warning("attempt %d/%d invalid response: %s", attempt, self.settings.max_retries, last_err)
                messages = messages + [
                    {"role": "assistant", "content": last_raw},
                    {
                        "role": "user",
                        "content": f"Your previous response was invalid: {last_err}\n"
                        "Return corrected JSON only. source_quote must be copied verbatim from the CLAUSE TEXT.",
                    },
                ]
        raise ExtractionFailure(last_err, last_raw)


# --------------------------------------------------------------------------------------
# Optional LLM helpers for the resolution pass
# --------------------------------------------------------------------------------------
class RelationJudgement(BaseModel):
    relation: str = "NONE"  # SUPPORTS | CONTRADICTS | QUALIFIES | EXCEPTS_FROM | REFERS_TO | NONE
    direction: str = "a_to_b"  # a_to_b | b_to_a
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class ReferenceJudgement(BaseModel):
    chosen_id: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class OllamaJudge:
    """Pairwise relation classification and reference adjudication, using the same model."""

    def __init__(self, settings: Settings, backend: Optional[ChatBackend] = None):
        settings.require_model()
        self.settings = settings
        self.backend = backend or default_backend(settings)
        self.method = f"llm:{settings.ollama_model}"

    def _ask(self, system: str, user: str, model_cls: type[BaseModel]) -> Optional[BaseModel]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for _ in range(self.settings.max_retries):
            try:
                resp = self.backend.chat(
                    model=self.settings.ollama_model,
                    messages=messages,
                    format=model_cls.model_json_schema(),
                    options={"temperature": 0},
                )
                return model_cls.model_validate(json.loads(_content(resp)))
            except Exception as exc:
                log.warning("judge call failed: %s", exc)
        return None

    def classify(self, a, b) -> Optional[RelationJudgement]:
        system = (
            "You compare two contract propositions, A and B. Decide if A relates to B as one of: "
            "SUPPORTS, CONTRADICTS, QUALIFIES, EXCEPTS_FROM, REFERS_TO, or NONE. Use direction a_to_b when A is "
            "the source of the relation, b_to_a otherwise. Be conservative: answer NONE unless the text clearly "
            "supports the link. Respond with JSON only."
        )
        user = (
            f"A ({a.modality.value}): {a.normalized_text}\nA quote: {a.source_quote}\n\n"
            f"B ({b.modality.value}): {b.normalized_text}\nB quote: {b.source_quote}"
        )
        return self._ask(system, user, RelationJudgement)  # type: ignore[return-value]

    def adjudicate(self, prop, ref, candidates) -> Optional[ReferenceJudgement]:
        system = (
            "A contract proposition contains a reference to something earlier. Choose which candidate it refers to "
            "by id, or null if it is genuinely ambiguous. Never guess. Respond with JSON only."
        )
        cand = "\n".join(f"- {c.proposition_id}: {c.normalized_text}" for c in candidates)
        user = f"Reference: \"{ref.surface_text}\"\nIn: {prop.source_quote}\n\nCandidates:\n{cand}"
        return self._ask(system, user, ReferenceJudgement)  # type: ignore[return-value]
