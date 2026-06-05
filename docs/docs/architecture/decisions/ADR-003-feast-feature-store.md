# ADR-003: Decide Against Feast Feature Store

**Status**: Rejected  
**Date**: 2026-02-14  
**Deciders**: Platform team

---

## Context

During Phase 1 design, the team evaluated whether to adopt **Feast** as a feature store for the platform. A feature store manages the lifecycle of ML features — ensuring consistency between training and serving, enabling feature reuse across models, and providing point-in-time correct lookups.

The team considered feature store adoption because:
- MLflow tracks model artefacts and metrics but does not manage input features.
- Without a feature store, training and serving pipelines must independently re-derive features, risking training-serving skew.
- A feature store is considered MLOps best practice for production ML systems.

---

## Decision

**We will not adopt Feast** for this platform.

The platform's two ML models (captioner and storyteller) are both inference-only — neither model is trained on structured feature vectors derived from a feature store. Their inputs are:
- **Captioner**: raw image bytes (PIL Image).
- **Storyteller**: natural-language caption + style metadata.

Neither input type maps naturally to the tabular/time-series feature model that Feast is designed for. Feast excels at serving precomputed numerical features (embeddings, aggregated statistics, user profile features) — not image pixels or free-text strings.

---

## Alternatives Considered

### Feast with image embedding features
- **Approach**: Pre-compute image embeddings offline with a frozen CLIP model and store them in Feast's online store. Use embeddings as input features to a downstream classifier.
- **Rejected because**: The platform uses BLIP-2 for generative captioning, not classification. The embeddings would be an intermediate step that adds infrastructure complexity without improving the generative output quality.

### Tecton (managed feature store)
- **Rejected because**: Cloud SaaS — violates the local-only data processing constraint.

### Hopsworks
- **Pros**: Strong open-source feature store with a free tier.
- **Rejected because**: Adds a Java-based Hopsworks server to the local stack. For two models with no tabular features, the operational overhead is not justified.

---

## Consequences

**Positive**:
- Significantly simpler local development stack — no feature store service to run and maintain.
- Removes a class of training-serving skew risks that do not apply to this architecture (there is no periodic re-training on user data in Phase 1–3).

**Negative**:
- If the platform evolves to include personalisation features (e.g., per-child style preference models trained on interaction data), the absence of a feature store will become a gap. The team should revisit this decision at that point.

**Mitigation**: The `ComicState` TypedDict and `ComicSchema` Pydantic model act as a lightweight, typed data contract across pipeline stages, providing the consistency guarantees that a feature store would otherwise supply at a structural level.
