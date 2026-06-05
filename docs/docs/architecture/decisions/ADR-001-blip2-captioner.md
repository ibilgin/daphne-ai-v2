# ADR-001: Use BLIP-2 as the Drawing Captioner

**Status**: Accepted  
**Date**: 2026-01-10  
**Deciders**: Platform team

---

## Context

The platform needs to convert a child's freehand drawing into a natural-language caption before the story generation pipeline can begin. The quality and style of this caption directly determines the narrative produced downstream.

Key constraints:
- Must run locally (no cloud API calls; child data must not leave the machine).
- Must handle low-quality, ambiguous, or abstract children's drawings gracefully.
- Must be integrable with MLflow `pyfunc` for experiment tracking and model versioning.
- Inference latency should be under 30 seconds on a CPU-only machine.

---

## Decision

We adopt **Salesforce BLIP-2** (specifically `Salesforce/blip2-opt-2.7b`) as the image-captioning backbone, wrapped in an MLflow `pyfunc` model class (`CaptionerModel` in `backend/models/captioner.py`).

The model is loaded once at worker startup and cached in memory. Image pre-processing is handled by the HuggingFace `transformers` `Blip2Processor`.

---

## Alternatives Considered

### CLIP (OpenAI)
- **Pros**: Extremely fast, robust zero-shot image–text matching.
- **Cons**: CLIP is an embedding model, not a generative captioner. It cannot produce free-form narrative descriptions from a drawing — it ranks candidate texts. Not suitable without a large candidate corpus.

### LLaVA (Large Language and Vision Assistant)
- **Pros**: State-of-the-art vision-language understanding, capable of nuanced scene descriptions.
- **Cons**: Minimum model size is 7B parameters. On CPU-only hardware this exceeds the 30-second latency constraint by an order of magnitude. Requires significant GPU VRAM for practical use.

### Microsoft Florence-2
- **Pros**: Smaller than LLaVA, strong captioning.
- **Cons**: Less mature HuggingFace integration at decision time; limited documentation for pyfunc wrapping.

---

## Consequences

**Positive**:
- BLIP-2 2.7B is small enough to run on CPU-only hardware within latency constraints.
- HuggingFace integration is well-documented and stable.
- Wrapping as an MLflow pyfunc enables quality gating (METEOR > 0.35, BERTScore F1 > 0.75) and reproducible experiment tracking.

**Negative**:
- Captions for highly abstract drawings may be vague ("a colourful image", "a drawing of shapes"). The downstream story pipeline must handle this gracefully via the RAG fallback.
- The 2.7B model requires ~6 GB RAM — teams with less than 8 GB RAM may experience swap-induced slowdowns.

**Mitigation**: The storytelling pipeline uses ChromaDB RAG retrieval with the caption as the query, meaning even a vague caption will pull relevant style exemplars that ground the narrative.
