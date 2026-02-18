"""
Integrated RCA Tool - Domain Agents + 5 Whys Pipeline

Orchestrates sequential execution:
1. Run domain agents in parallel
2. Aggregate domain insights
3. Run enhanced 5 Whys with domain context
4. Return comprehensive root cause analysis
"""

from typing import List, Dict, Any, Optional
import asyncio
import logging

from tools.base_tool import BaseTool
from models.tool_results import ToolResult, DomainInsightsSummary, DomainAnalysisResult
from domain_agents import MechanicalAgent, ElectricalAgent, ProcessAgent
from tools.five_whys_tool import FiveWhysTool

logger = logging.getLogger(__name__)


class IntegratedRCATool(BaseTool):
    """
    Integrated RCA pipeline combining domain agents and 5 Whys.
    
    Executes a sequential analysis:
    1. Domain agents analyze failure (parallel execution)
    2. Aggregate domain insights
    3. Enhanced 5 Whys uses domain insights + RAG
    4. Return comprehensive, domain-backed root cause
    """
    
    def __init__(self, llm_adapter: Any, rag_manager: Any):
        super().__init__(llm_adapter, rag_manager, tool_name="integrated_rca")
        
        # Initialize domain agents
        self.mechanical_agent = MechanicalAgent(llm_adapter, rag_manager)
        self.electrical_agent = ElectricalAgent(llm_adapter, rag_manager)
        self.process_agent = ProcessAgent(llm_adapter, rag_manager)
        
        # Initialize 5 Whys tool
        self.five_whys = FiveWhysTool(llm_adapter, rag_manager)
        
        # Agent routing keywords
        self.agent_routing = {
            "mechanical_agent": [
                "bearing", "vibration", "mechanical", "wear", "alignment",
                "shaft", "coupling", "lubrication", "fatigue", "corrosion",
                "gearbox", "impeller", "belt", "chain", "girth gear"
            ],
            "electrical_agent": [
                "motor", "electrical", "power", "current", "voltage",
                "interlock", "relay", "trip", "overcurrent", "VFD",
                "winding", "insulation", "contactor", "circuit", "fuse"
            ],
            "process_agent": [
                "temperature", "pressure", "flow", "process", "combustion",
                "emission", "feed", "composition", "setpoint", "heat",
                "flame", "damper", "draft", "kiln speed"
            ]
        }
    
    async def analyze(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        **kwargs
    ) -> ToolResult:
        """
        Execute integrated RCA pipeline.
        
        Steps:
        1. Route to appropriate domain agents
        2. Run domain agents in parallel
        3. Aggregate domain insights
        4. Run 5 Whys with domain context
        5. Return comprehensive result
        
        Args:
            failure_description: Description of the failure
            equipment_name: Name of the equipment
            symptoms: List of observed symptoms
            **kwargs: Additional parameters (status_callback, etc.)
            
        Returns:
            ToolResult containing integrated analysis
        """
        status_callback = kwargs.get("status_callback")
        
        async def _send_status(msg: str):
            if status_callback:
                await status_callback(msg)
        
        async def _perform_analysis():
            # Step 1: Route to domain agents
            await _send_status("🔍 Routing to domain experts...")
            selected_agents = self._route_agents(failure_description, symptoms)
            await _send_status(f"✓ Selected experts: {', '.join([a.replace('_agent', '').title() for a in selected_agents])}")
            
            # Step 2: Run domain agents in parallel
            await _send_status("🔬 Domain experts analyzing failure...")
            domain_results = await self._run_domain_agents(
                selected_agents,
                failure_description,
                equipment_name,
                symptoms,
                status_callback
            )
            
            # Step 3: Aggregate domain insights
            await _send_status("📊 Aggregating domain expert insights...")
            domain_insights = self._aggregate_domain_insights(domain_results)
            await _send_status(
                f"✓ Domain analysis complete — {len(domain_insights.key_findings)} "
                f"key findings identified (avg confidence: {domain_insights.overall_confidence*100:.0f}%)"
            )
            
            # Send domain summary to user
            await _send_status("\n--- DOMAIN EXPERT ANALYSIS SUMMARY ---")
            for finding in domain_insights.key_findings[:3]:
                await _send_status(f"  • {finding}")
            await _send_status("")
            
            # Step 4: Run enhanced 5 Whys
            await _send_status("🎯 Starting main root cause analysis (5 Whys)...")
            await _send_status("Using domain expert insights as foundation...")
            
            five_whys_result = await self.five_whys.analyze(
                failure_description=failure_description,
                equipment_name=equipment_name,
                symptoms=symptoms,
                domain_insights=domain_insights,  # Pass domain context
                status_callback=status_callback
            )
            
            # Step 5: Build comprehensive result
            return {
                "domain_insights": domain_insights.model_dump(),
                "five_whys_analysis": five_whys_result.result,
                "final_root_cause": five_whys_result.result["root_cause"],
                "final_confidence": five_whys_result.result["root_cause_confidence"],
                "analysis_method": "domain_enhanced_5_whys",
                "agents_used": selected_agents
            }
        
        return await self._execute_with_timing(_perform_analysis)
    
    def _route_agents(self, failure_description: str, symptoms: List[str]) -> List[str]:
        """Route to appropriate domain agents based on keywords."""
        text = f"{failure_description} {' '.join(symptoms)}".lower()
        
        selected = []
        for agent_name, keywords in self.agent_routing.items():
            if any(kw in text for kw in keywords):
                selected.append(agent_name)
        
        # Default to mechanical if no match
        if not selected:
            selected.append("mechanical_agent")
        
        return selected
    
    async def _run_domain_agents(
        self,
        agent_names: List[str],
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        status_callback
    ) -> List[ToolResult]:
        """Run selected domain agents in parallel."""
        
        async def _run_one(agent_name: str):
            agent = getattr(self, agent_name)
            return await agent.analyze(
                failure_description=failure_description,
                equipment_name=equipment_name,
                symptoms=symptoms,
                status_callback=status_callback
            )
        
        tasks = [_run_one(name) for name in agent_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out failures
        valid_results = [r for r in results if isinstance(r, ToolResult) and r.success]
        
        if not valid_results:
            self.logger.warning("All domain agents failed, will fallback to RAG-only 5 Whys")
        
        return valid_results
    
    def _aggregate_domain_insights(self, results: List[ToolResult]) -> DomainInsightsSummary:
        """Aggregate insights from all domain agents."""
        
        if not results:
            # Return empty insights if all agents failed
            return DomainInsightsSummary(
                agents_analyzed=[],
                domain_analyses=[],
                key_findings=["No domain analysis available - using RAG-only mode"],
                suspected_root_causes=[],
                recommended_checks=[],
                documents_used=[],
                overall_confidence=0.5
            )
        
        agents_analyzed = []
        domain_analyses = []
        all_findings = []
        suspected_causes = []
        all_checks = []
        all_docs = []
        confidences = []
        
        for result in results:
            analysis = result.result
            agents_analyzed.append(analysis["domain"])
            domain_analyses.append(DomainAnalysisResult(**analysis))
            
            # Extract critical findings
            for finding in analysis["findings"]:
                if finding["severity"] == "critical":
                    all_findings.append(
                        f"[{analysis['domain'].upper()}] {finding['observation']} (CRITICAL)"
                    )
                elif finding["severity"] == "warning" and len(all_findings) < 10:
                    all_findings.append(
                        f"[{analysis['domain'].upper()}] {finding['observation']} (WARNING)"
                    )
            
            # Extract suspected root causes
            suspected_causes.append({
                "domain": analysis["domain"],
                "hypothesis": analysis["root_cause_hypothesis"],
                "confidence": analysis["confidence"]
            })
            
            # Collect checks and documents
            all_checks.extend(analysis.get("recommended_checks", []))
            all_docs.extend(analysis.get("documents_used", []))
            confidences.append(analysis["confidence"])
        
        # Calculate overall confidence (weighted average)
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.5
        
        return DomainInsightsSummary(
            agents_analyzed=agents_analyzed,
            domain_analyses=domain_analyses,
            key_findings=all_findings[:10],  # Top 10
            suspected_root_causes=suspected_causes,
            recommended_checks=list(set(all_checks))[:10],  # Unique, top 10
            documents_used=list(set(all_docs)),
            overall_confidence=overall_confidence
        )
