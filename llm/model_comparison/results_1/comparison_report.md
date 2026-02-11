# AI Model Comparison Report

**Generated:** 2026-02-09 00:12:09

**Models Tested:**
- OpenAI GPT-4o
- Google Gemini 3 Flash

**Scenarios:** 2

---

## Summary Comparison

| Model | Scenario | Avg Response Time | Avg Cost | Total Cost |
|-------|----------|-------------------|----------|------------|
| OpenAI (No RAG) | All | 3.61s | $0.0000 | $0.0000 |
| OpenAI (With RAG) | All | 3.77s | $0.0000 | $0.0000 |
| Gemini (No RAG) | All | 12.55s | $0.0002 | $0.0004 |
| Gemini (With RAG) | All | 7.87s | $0.0002 | $0.0004 |

---

## Detailed Results

### Scenario 1: Rotary Kiln Bearing Overheating

**Equipment:** Rotary Kiln  
**Description:** The rotary kiln support roller bearing temperature increased from normal 65°C to 95°C over 2 hours. Kiln was shut down as a precaution when temperature reached 100°C alarm setpoint.

#### OpenAI GPT-4o (Without RAG)
- **Root Cause:** Error: Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}
- **Response Time:** 4.03s
- **Cost:** $0.0000

#### OpenAI GPT-4o (With RAG)
- **Root Cause:** Error: Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}
- **RAG Docs Retrieved:** 0
- **Response Time:** 4.70s
- **Cost:** $0.0000

#### Google Gemini Pro (Without RAG)
- **Root Cause:** **Failure of the Hydrodynamic Lubricant Film due to Water Contamination or Oil Degradation, leading to Bearing Surface Spalling (Metal-to-Metal Contact).**
- **Response Time:** 20.03s
- **Cost:** $0.0004

#### Google Gemini Pro (With RAG)
- **Root Cause:** Error: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'The model is overloaded. Please try again later.', 'status': 'UNAVAILABLE'}}
- **RAG Docs Retrieved:** 0
- **Response Time:** 2.63s
- **Cost:** $0.0000

---

### Scenario 2: ID&HR Fan Motor Overcurrent Trip

**Equipment:** ID&HR Fan  
**Description:** The induced draft fan motor tripped on overcurrent protection. Motor current was observed at 420A against rated 380A before trip. Fan was running normally before the incident.

#### OpenAI GPT-4o (Without RAG)
- **Root Cause:** Error: Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}
- **Response Time:** 3.20s
- **Cost:** $0.0000

#### OpenAI GPT-4o (With RAG)
- **Root Cause:** Error: Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}
- **RAG Docs Retrieved:** 0
- **Response Time:** 2.84s
- **Cost:** $0.0000

#### Google Gemini Pro (Without RAG)
- **Root Cause:** Error: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'The model is overloaded. Please try again later.', 'status': 'UNAVAILABLE'}}
- **Response Time:** 5.08s
- **Cost:** $0.0000

#### Google Gemini Pro (With RAG)
- **Root Cause:** **Increased Mass Flow due to High Gas Density (Low Process Temperature) or Upstream Air Ingress.**
- **RAG Docs Retrieved:** 0
- **Response Time:** 13.11s
- **Cost:** $0.0004

---

## Recommendation

**Recommended Model:** OpenAI GPT-4o

- **Total Cost:** $0.0000 vs $0.0009

---

## Next Steps

1. Review detailed results in JSON files
2. Evaluate quality of responses for your use case
3. Consider cost vs quality trade-offs
4. Purchase API credits for chosen model
5. Proceed with Phase 2 implementation
