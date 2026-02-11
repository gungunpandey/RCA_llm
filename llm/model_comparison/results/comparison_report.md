# AI Model Comparison Report

**Generated:** 2026-02-09 00:50:48

**Models Tested:**
- Azure OpenAI GPT-4.1
- Google Gemini 3 Flash

**Scenarios:** 2

---

## Summary Comparison

| Model | Scenario | Avg Response Time | Avg Cost | Total Cost |
|-------|----------|-------------------|----------|------------|
| Azure (No RAG) | All | 1.23s | $0.0000 | $0.0000 |
| Azure (With RAG) | All | 0.81s | $0.0000 | $0.0000 |
| Gemini (No RAG) | All | 8.87s | $0.0002 | $0.0004 |
| Gemini (With RAG) | All | 17.54s | $0.0016 | $0.0033 |

---

## Detailed Results

### Scenario 1: Rotary Kiln Bearing Overheating

**Equipment:** Rotary Kiln  
**Description:** The rotary kiln support roller bearing temperature increased from normal 65Â°C to 95Â°C over 2 hours. Kiln was shut down as a precaution when temperature reached 100Â°C alarm setpoint.

#### Azure OpenAI GPT-4.1 (Without RAG)
- **Root Cause:** Error: Error code: 404 - {'error': {'code': 'DeploymentNotFound', 'message': 'The API deployment for this resource does not exist. If you created the deployment within the last 5 minutes, please wait a moment and try again.'}}
- **Response Time:** 1.39s
- **Cost:** $0.0000

#### Azure OpenAI GPT-4.1 (With RAG)
- **Root Cause:** Error: Error code: 404 - {'error': {'code': 'DeploymentNotFound', 'message': 'The API deployment for this resource does not exist. If you created the deployment within the last 5 minutes, please wait a moment and try again.'}}
- **RAG Docs Retrieved:** 5
- **Response Time:** 1.17s
- **Cost:** $0.0000

#### Google Gemini Pro (Without RAG)
- **Root Cause:** ** 
Failure of the internal lubrication delivery system (specifically a detached or damaged oil bucket/scoop) or a sudden shift in axial thrust causing "wiping" of the bearing thrust face.

**REASONING:**
1.  **Rapid Temperature Gradient:** A rise of 30°C in only two hours is indicative of a "thermal runaway" condition. This suggests that the hydrodynamic oil film, which usually separates the shaft from the bearing liner, has been compromised, leading to metal-to-metal contact.
2.  **Normal Oil Level vs. High Temp:** The fact that the oil level is normal rules out a catastrophic leak. However, a "normal level" does not mean the oil is reaching the load zone. In rotary kiln support rollers (which usually use oil scoops/buckets to lift oil to the top of the journal), a mechanical failure of a scoop would mean the bearing is "starved" despite the sump being full.
3.  **Noise and Vibration:** These symptoms are classic indicators of mechanical interference. The noise likely stems from the "scuffing" or "galling" of the white metal (babbitt) or bronze bushing. The slight vibration increase suggests that the friction is causing a stick-slip effect or that the bearing surface has already begun to deform/smear (wiping).
4.  **Axial Thrust Component:** Rotary kilns are designed to move axially. If the kiln shifted suddenly (due to changes in coating, temperature, or mechanical "skew" of other rollers), the thrust collar of the roller may be pressed too hard against the bearing face. If the lubrication film at that specific thrust interface fails, heat generates rapidly at that localized point and conducts through the entire housing.

**CONFIDENCE:** 85% 
*(Note: A 100% diagnosis would require an oil analysis report and a visual inspection of the internal scoops and the thrust collar.)*

**CORRECTIVE ACTIONS:**
1.  **Immediate Inspection (Internal):** Open the bearing housing inspection covers to check the condition of the oil scoops/buckets. Ensure they are securely fastened and effectively delivering oil to the top of the journal.
2.  **Oil Quality Analysis:** Take a sample of the lubricant immediately. Check for the presence of "white metal" or bronze particles (indicating bearing wear) and check for "darkening" or burnt odor (indicating thermal oxidation).
3.  **Check Kiln Axial Position:** Verify the kiln's position relative to the thrust rollers. If the kiln is "heavy" on the downhill side, it may be overloading the thrust face of this specific support roller. Adjusting the roller "skew" (bore-sighting) may be necessary to relieve pressure.
4.  **Bearing Surface Restoration:** If the temperature reached 100°C, the babbitt (white metal) has likely undergone "wiping." The bearing should be dismantled, and the high spots/scuff marks should be hand-scraped to restore the hydrodynamic oil grooves.
5.  **Cooling System Verification:** If the bearing is water-cooled, check for scale buildup or airlocks in the cooling coils that might have reduced heat dissipation efficiency during a minor friction event.
- **Response Time:** 15.07s
- **Cost:** $0.0004

#### Google Gemini Pro (With RAG)
- **Root Cause:** ** Internal mechanical failure/damage of the support roller bearing (likely spalling or fatigue of the rolling elements or races), potentially exacerbated by lubricant contamination or excessive axial force (skew).

**REASONING:**
1.  **Symptom Triad:** The simultaneous occurrence of a rapid temperature rise (30°C increase in just 2 hours), unusual noise, and increased vibration is a classic indicator of physical degradation of the bearing's internal components.
2.  **Exclusion of Lubricant Starvation:** Documentation (and your report) indicates that the oil level is normal. This suggests the issue is not a simple lack of oil, but rather the performance of the bearing itself or the quality of the lubricant (Doc 5 mentions "misusage and deterioration of grease" or "impurities" as causes for overheating).
3.  **Threshold Violation:** According to Document 4, the highest allowable temperature for the rolling bearing is 80°C. The equipment reached 100°C, indicating a severe deviation from the "normal working condition."
4.  **Mechanical Correlation:** Document 5 explicitly links "Noise of thrust roller bearing" to "Damaged bearing." While this is a support roller, the mechanical principles remain the same: noise and vibration in a bearing housing typically result from irregular surfaces on the rollers or races, which generates friction and leads to the rapid heat spikes observed.
5.  **Alignment Factors:** Document 5 also suggests that "incorrect skew of roller station" creates excessive force. This excessive force can cause the bearing to fail prematurely, leading to the noise and vibration reported.

**CONFIDENCE:** 85%
*(High confidence in mechanical damage; the remaining 15% uncertainty accounts for potential external heat radiation from a kiln shell "hot spot" near the bearing, though that would not typically cause noise and vibration.)*

**CORRECTIVE ACTIONS:**
1.  **Immediate Internal Inspection:** Open the bearing housing (as per Document 1/2, "lift off the upper housing member") to inspect the rolling elements, cage, and races for signs of pitting, spalling, or discoloration from heat.
2.  **Debris Analysis:** Check the existing grease/oil for metal particles or contaminants. If found, this confirms internal mechanical failure.
3.  **Check Roller Alignment (Skew):** Verify the "parallelism" of the roller station relative to the kiln shell center line (Doc 4/5). If the roller is incorrectly skewed, it must be adjusted to reduce axial thrust.
4.  **Bearing Replacement:** If physical damage (spalling/cracking) is detected, replace the bearing entirely as recommended in the troubleshooting table (Doc 5).
5.  **Lubrication System Flush:** Before restarting with a new bearing, clean the grease pipes and housing thoroughly to ensure no residual metal shavings remain to contaminate the new lubricant (Doc 5: "Clean grease pipe, repair lubricating unit").
6.  **Insulation Check:** Inspect the heat-insulating unit near the bearing (Doc 5) to ensure local kiln shell heat is not contributing to the bearing's thermal load.
- **RAG Docs Retrieved:** 5
- **Response Time:** 13.64s
- **Cost:** $0.0018

---

### Scenario 2: ID&HR Fan Motor Overcurrent Trip

**Equipment:** ID&HR Fan  
**Description:** The induced draft fan motor tripped on overcurrent protection. Motor current was observed at 420A against rated 380A before trip. Fan was running normally before the incident.

#### Azure OpenAI GPT-4.1 (Without RAG)
- **Root Cause:** Error: Error code: 404 - {'error': {'code': 'DeploymentNotFound', 'message': 'The API deployment for this resource does not exist. If you created the deployment within the last 5 minutes, please wait a moment and try again.'}}
- **Response Time:** 1.07s
- **Cost:** $0.0000

#### Azure OpenAI GPT-4.1 (With RAG)
- **Root Cause:** Error: Error code: 404 - {'error': {'code': 'DeploymentNotFound', 'message': 'The API deployment for this resource does not exist. If you created the deployment within the last 5 minutes, please wait a moment and try again.'}}
- **RAG Docs Retrieved:** 5
- **Response Time:** 0.45s
- **Cost:** $0.0000

#### Google Gemini Pro (Without RAG)
- **Root Cause:** Error: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'The model is overloaded. Please try again later.', 'status': 'UNAVAILABLE'}}
- **Response Time:** 2.67s
- **Cost:** $0.0000

#### Google Gemini Pro (With RAG)
- **Root Cause:** ** Process Overload due to excessive mass flow, likely caused by the inlet damper being opened too far (75%) for the prevailing gas density (low temperature) conditions.

**REASONING:**
1.  **Exclusion of Mechanical Failure:** The fan vibration was recorded within normal limits according to ISO 10816-3 (as referenced in Document 1). This rules out mechanical causes such as bearing seizure, impeller unbalance, or significant blade fouling, which would typically manifest as high vibration before an overcurrent trip.
2.  **Identification of Electrical Overload:** The motor current was 420A, significantly exceeding the rated 380A. This confirms the trip was a result of a sustained thermal/electrical overload rather than a sudden short circuit or a logic-based interlock trip (such as the ESP interlocks mentioned in Documents 2-5).
3.  **Analysis of System Draft and Flow:** The "higher than normal" system draft pressure combined with high motor current is a classic indicator of high mass flow in a centrifugal fan. In these systems, motor power consumption is directly proportional to the density of the gas and the volume of air moved.
4.  **Impact of Damper Position and Gas Density:**
    *   The inlet damper was at 75% open. For an ID (Induced Draft) fan, which is usually designed to handle hot, low-density flue gases, operating at 75% open with cooler (denser) air—such as during a cold start or a process temperature drop—will cause the motor to exceed its rated horsepower.
    *   Since the "System draft was higher than normal," the fan was successfully moving a larger mass of air than the motor was designed to support at that specific damper setting.
5.  **Correlation with Documentation:** While Documents 2-5 detail various ESP interlocks (CO levels, hopper temperatures, RAV status), these typically trigger a "Command Trip" through the control system. The fact that the motor specifically tripped on **overcurrent protection** suggests the failure was physical/aerodynamic load exceeding the motor's nameplate capacity, not a logic-initiated shutdown.

**CONFIDENCE:** 85%

**CORRECTIVE ACTIONS:**
1.  **Operational Procedure Revision:** Implement a "Cold Start" or "Low Temperature" limit on the ID Fan inlet damper. The damper should be restricted to a lower percentage (e.g., <30-40%) until the flue gas reaches design operating temperatures to prevent overcurrent.
2.  **Control System Interlock:** Program a "Current Limiting" function in the PLC/DCS that automatically modulates the inlet damper closed if the motor current exceeds 370A (just below rated).
3.  **Damper Calibration:** Inspect and calibrate the inlet damper actuator and feedback link to ensure that "75% open" in the control room matches the actual physical position of the vanes.
4.  **Review Protection Settings:** Verify that the motor protection relay's inverse-time overcurrent curve (51) is correctly coordinated with the motor's thermal withstand capability to prevent nuisance trips while still providing protection.
5.  **Temperature Monitoring:** Cross-reference the flue gas temperature at the time of the trip to confirm if a sudden drop in temperature (and subsequent increase in density) coincided with the current spike.
- **RAG Docs Retrieved:** 5
- **Response Time:** 21.45s
- **Cost:** $0.0015

---

## Recommendation

**Recommended Model:** Azure OpenAI GPT-4.1

- **Total Cost:** $0.0000 vs $0.0037

---

## Next Steps

1. Review detailed results in JSON files
2. Evaluate quality of responses for your use case
3. Consider cost vs quality trade-offs
4. Purchase API credits for chosen model
5. Proceed with Phase 2 implementation
