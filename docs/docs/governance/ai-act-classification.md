# EU AI Act Classification

## Classification: Limited Risk

**System**: Sketch to Story — AI comic book generator  
**Classification date**: 2026-01-15  
**Reviewed by**: Platform team  
**Next review**: 2027-01-15

---

## Classification Rationale

Under the EU AI Act (Regulation 2024/1689), AI systems are classified according to their risk level:

| Risk Level | Definition | Examples |
|-----------|------------|---------|
| Unacceptable | Prohibited practices | Social scoring, real-time biometric surveillance |
| High | Safety-critical or fundamental rights impact | Medical devices, critical infrastructure, biometric categorisation |
| **Limited** | **Specific transparency obligations** | **Chatbots, deepfakes, AI-generated content** |
| Minimal | No specific obligations | AI-enabled spam filters, video games |

**Sketch to Story is classified as Limited Risk** for the following reasons:

1. **It generates creative content** (comic stories) that is presented to users — this triggers the AI-generated content transparency requirement under Article 50.
2. **It does not make consequential decisions** about individuals. No automated decision-making with legal or similarly significant effects occurs.
3. **It is not a high-risk system** under Annex III — it does not operate in any of the regulated domains (healthcare, law enforcement, education assessment, employment, etc.).
4. **It processes children's data**, which triggers additional obligations beyond the base Limited Risk classification (see below).

---

## Transparency Obligations (Article 50)

As an AI system that generates text and image content, the platform must:

### Obligation 1: Disclose AI involvement

A clear, prominent notice must inform users (parents/educators) that the comic story and narration are AI-generated **before** generation begins.

**Implementation**: The `GenerateView` wizard displays a transparency notice on the first step that must be acknowledged before proceeding.

---

### Obligation 2: AI-generated content marking

The generated comic must be marked as AI-generated content in a machine-readable format.

**Implementation**: All comics include metadata: `{"ai_generated": true, "models": ["captioner", "storyteller"], "platform": "Sketch to Story"}` in the comic JSON and the HTML export footer.

---

## Additional Obligations: Children's Data Processing

Processing personal data of children triggers obligations under:
- **GDPR Article 8** (children's consent — operator must obtain parental consent)
- **GDPR Article 25** (data protection by design and by default)
- **EU AI Act Recital 48** (heightened protection for vulnerable groups)

### Data minimisation (GDPR Article 5(1)(c))

Only the minimum data necessary for the service is collected:

| Data | Purpose | Retention |
|------|---------|-----------|
| Drawing image | Caption extraction (in-memory only) | Not stored |
| Child's first name | Comic cover title personalisation | Stored in comic record |
| Age group | Age-appropriate story generation | Stored in comic record |
| SHA-256 hash of child name | Audit trail de-identification | Audit log, indefinite |

Raw image bytes are **never written to disk or database**. This is enforced by code convention and verified by integration tests.

---

### Purpose limitation (GDPR Article 5(1)(b))

Data collected for comic generation is used **only** for comic generation. It is not used for:
- Model training (no personal data enters training pipelines)
- User profiling or behavioural analytics
- Third-party sharing

---

### Transparency to data subjects (GDPR Article 13/14)

A privacy notice (accessible from the footer of the application) must explain in plain language:
- What data is collected
- How it is used
- How long it is retained
- How to request deletion

---

### Human oversight for escalated cases

Cases where the automated safety gate detects content in the 0.08–0.10 toxicity range (edge cases) are queued for human review within 48 hours before the comic is delivered. This implements the human oversight requirement under EU AI Act Article 14.

---

## Non-Applicability of High-Risk Classification

The following Annex III high-risk categories were reviewed and do not apply:

| Annex III Category | Applies? | Reasoning |
|-------------------|----------|-----------|
| Biometric categorisation | No | No biometric data processed |
| Critical infrastructure | No | Entertainment application |
| Education / vocational training | No | Not used for assessment or scoring |
| Employment | No | Not used for recruitment or performance evaluation |
| Essential services | No | Not credit, benefits, or emergency services |
| Law enforcement | No | No policing application |
| Migration / border control | No | Not applicable |
| Administration of justice | No | Not applicable |

---

## Governance Contact

For questions about this classification or to request a re-evaluation, contact the platform governance team. Any change to the system's scope or capabilities that might affect this classification must trigger a re-evaluation before deployment.
