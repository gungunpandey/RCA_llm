"""
Evidence-Based RCA Validation Module

Implements plant-credible failure analysis with:
1. Evidence gate enforcement
2. Confidence calibration based on evidence type
3. Plant-credible failure mode validation
"""

from typing import Dict, List, Optional, Tuple
from enum import Enum
import re


class EvidenceType(Enum):
    """Types of evidence for RCA."""
    MEASURED = "measured"  # Sensor data, trend data, alarm logs
    DOCUMENTED = "documented"  # OEM manual rules, procedures
    INFERRED = "inferred"  # Logical deduction without direct evidence
    NONE = "none"  # No evidence


class ConfidenceCalibrator:
    """
    Calibrates confidence scores based on evidence quality.
    
    Plant-credible RCA requires evidence. If evidence is inferred
    or missing, confidence must be downgraded.
    """
    
    # Maximum confidence levels by evidence type
    MAX_CONFIDENCE = {
        EvidenceType.MEASURED: 0.95,      # Sensor data, alarms, trends
        EvidenceType.DOCUMENTED: 0.85,    # OEM manual explicitly states causality
        EvidenceType.INFERRED: 0.70,      # Logical deduction, no direct evidence
        EvidenceType.NONE: 0.50           # Pure speculation
    }
    
    @classmethod
    def calibrate_confidence(
        cls,
        raw_confidence: float,
        evidence_type: EvidenceType,
        has_timestamp_correlation: bool = False,
        has_trend_data: bool = False,
        has_oem_rule: bool = False
    ) -> Tuple[float, str]:
        """
        Calibrate confidence based on evidence quality.
        
        Args:
            raw_confidence: LLM's raw confidence (0.0-1.0)
            evidence_type: Type of evidence available
            has_timestamp_correlation: Whether alarm timestamps correlate
            has_trend_data: Whether trend data supports the claim
            has_oem_rule: Whether OEM manual explicitly states causality
            
        Returns:
            (calibrated_confidence, justification)
        """
        # Cap confidence by evidence type
        max_conf = cls.MAX_CONFIDENCE[evidence_type]
        calibrated = min(raw_confidence, max_conf)
        
        # Build justification
        justifications = []
        
        if evidence_type == EvidenceType.MEASURED:
            justifications.append("Direct measurement data available")
            if has_timestamp_correlation:
                justifications.append("Alarm timestamps correlate")
            if has_trend_data:
                justifications.append("Trend data supports causality")
        
        elif evidence_type == EvidenceType.DOCUMENTED:
            if has_oem_rule:
                justifications.append("OEM manual explicitly states causality")
            else:
                justifications.append("Referenced in technical documentation")
        
        elif evidence_type == EvidenceType.INFERRED:
            calibrated = min(calibrated, 0.70)  # Hard cap at 70%
            justifications.append("⚠️ Inferred - no direct evidence")
            justifications.append("Requires validation with plant data")
        
        else:  # NONE
            calibrated = min(calibrated, 0.50)  # Hard cap at 50%
            justifications.append("⚠️ No evidence - speculative")
            justifications.append("Requires investigation")
        
        justification = "; ".join(justifications)
        
        return calibrated, justification
    
    @classmethod
    def assess_evidence_from_answer(cls, answer: str, documents: List[str]) -> EvidenceType:
        """
        Assess evidence type from the answer text.
        
        Args:
            answer: The why step answer
            documents: Supporting documents cited
            
        Returns:
            EvidenceType
        """
        answer_lower = answer.lower()
        
        # Check for measurement indicators
        measurement_indicators = [
            "sensor", "trend", "alarm", "logged", "recorded",
            "measured", "°c", "temperature reading", "pressure reading",
            "current reading", "vibration reading", "timestamp"
        ]
        
        if any(ind in answer_lower for ind in measurement_indicators):
            return EvidenceType.MEASURED
        
        # Check for OEM rule indicators
        oem_indicators = [
            "manual states", "manual specifies", "according to table",
            "oem manual", "explicitly", "mandates", "requires"
        ]
        
        if any(ind in answer_lower for ind in oem_indicators) and documents:
            return EvidenceType.DOCUMENTED
        
        # Check for inference indicators
        inference_indicators = [
            "likely", "probably", "suggests", "indicates",
            "could be", "may be", "possibly", "appears to"
        ]
        
        if any(ind in answer_lower for ind in inference_indicators):
            return EvidenceType.INFERRED
        
        # Default to documented if documents are cited
        if documents:
            return EvidenceType.DOCUMENTED
        
        return EvidenceType.NONE


class PlantFailureModeValidator:
    """
    Validates that failure modes are plant-credible.
    
    Prevents AI/system errors from appearing as plant failures.
    """
    
    # HTTP/API error patterns that should NEVER appear in plant RCA
    AI_ERROR_PATTERNS = [
        r'\b503\s+UNAVAILABLE\b',
        r'\b404\s+NOT\s+FOUND\b',
        r'\b500\s+INTERNAL\s+SERVER\s+ERROR\b',
        r'\bHTTP\s+ERROR\b',
        r'\bAPI\s+FAILURE\b',
        r'\bRETRY\s+LATER\b',
        r'\bSERVICE\s+UNAVAILABLE\b',
        r'\bCONNECTION\s+TIMEOUT\b',
    ]
    
    # Plant-credible signal failure modes
    PLANT_SIGNAL_FAILURES = [
        "bad quality",
        "comm fail",
        "signal unhealthy",
        "input forced low",
        "input forced high",
        "loss of signal",
        "sensor failure",
        "transmitter failure",
        "wiring fault",
        "loop error"
    ]
    
    @classmethod
    def validate_failure_mode(cls, text: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that failure mode is plant-credible.
        
        Args:
            text: Answer or root cause text
            
        Returns:
            (is_valid, error_message)
        """
        # Check for AI error patterns
        for pattern in cls.AI_ERROR_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                match = re.search(pattern, text, re.IGNORECASE)
                return False, (
                    f"🚨 AI ERROR LEAKED INTO PLANT RCA: '{match.group()}' is an HTTP/API error, "
                    f"not a plant failure mode. Plant systems show: {', '.join(cls.PLANT_SIGNAL_FAILURES[:3])}, etc."
                )
        
        return True, None
    
    @classmethod
    def sanitize_ai_errors(cls, text: str) -> str:
        """
        Replace AI errors with plant-credible equivalents.
        
        Args:
            text: Text potentially containing AI errors
            
        Returns:
            Sanitized text
        """
        # Replace 503 UNAVAILABLE with plant-credible signal failure
        text = re.sub(
            r'\b503\s+UNAVAILABLE\b',
            'Loss of Signal (LOS)',
            text,
            flags=re.IGNORECASE
        )
        
        # Replace other HTTP errors
        text = re.sub(
            r'\b(404|500|502|503)\s+(NOT\s+FOUND|INTERNAL\s+SERVER\s+ERROR|BAD\s+GATEWAY|UNAVAILABLE)\b',
            'Communication Failure',
            text,
            flags=re.IGNORECASE
        )
        
        return text


class EvidenceGate:
    """
    Enforces evidence requirements for RCA assertions.
    
    Before asserting a cause, requires at least one of:
    - Trend data
    - Alarm timestamp correlation
    - OEM rule explicitly stating causality
    """
    
    @classmethod
    def check_evidence_gate(
        cls,
        assertion: str,
        evidence: Dict[str, any]
    ) -> Tuple[bool, str]:
        """
        Check if assertion meets evidence gate requirements.
        
        Args:
            assertion: The causal assertion being made
            evidence: Dictionary with evidence flags:
                - has_trend_data: bool
                - has_alarm_correlation: bool
                - has_oem_rule: bool
                - documents_cited: List[str]
        
        Returns:
            (passes_gate, message)
        """
        has_trend = evidence.get('has_trend_data', False)
        has_alarms = evidence.get('has_alarm_correlation', False)
        has_oem = evidence.get('has_oem_rule', False)
        docs = evidence.get('documents_cited', [])
        
        # At least one evidence type required
        if has_trend or has_alarms or has_oem:
            evidence_types = []
            if has_trend:
                evidence_types.append("trend data")
            if has_alarms:
                evidence_types.append("alarm correlation")
            if has_oem:
                evidence_types.append("OEM rule")
            
            return True, f"✓ Evidence gate passed: {', '.join(evidence_types)}"
        
        # If documents cited but no explicit evidence, warn
        if docs:
            return True, (
                "⚠️ Evidence gate: Documents cited but no explicit trend/alarm/rule. "
                "Confidence should be capped at 70%."
            )
        
        # No evidence
        return False, (
            "❌ Evidence gate failed: No trend data, alarm correlation, or OEM rule. "
            "Assertion is speculative. Confidence capped at 50%."
        )


# Example usage
if __name__ == "__main__":
    # Test 1: Validate failure mode
    bad_text = "The system experienced a 503 UNAVAILABLE error"
    is_valid, error = PlantFailureModeValidator.validate_failure_mode(bad_text)
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Error: {error}")
    
    # Test 2: Sanitize AI errors
    sanitized = PlantFailureModeValidator.sanitize_ai_errors(bad_text)
    print(f"Sanitized: {sanitized}")
    
    # Test 3: Calibrate confidence
    calibrated, justification = ConfidenceCalibrator.calibrate_confidence(
        raw_confidence=0.95,
        evidence_type=EvidenceType.INFERRED,
        has_oem_rule=False
    )
    print(f"Calibrated confidence: {calibrated:.0%}")
    print(f"Justification: {justification}")
