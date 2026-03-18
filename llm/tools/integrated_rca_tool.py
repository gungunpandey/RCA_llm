"""
Integrated RCA Tool - Domain Agents + 5 Whys + Fishbone Pipeline

Orchestrates sequential execution:
1. Run domain agents in parallel
2. Aggregate domain insights
3. Run enhanced 5 Whys with domain context
4. Run Fishbone analysis using confirmed root cause
5. Return comprehensive root cause analysis
"""

from typing import List, Dict, Any, Optional
import asyncio
import logging

from tools.base_tool import BaseTool
from models.tool_results import ToolResult, DomainInsightsSummary, DomainAnalysisResult
from domain_agents import MechanicalAgent, ElectricalAgent, ProcessAgent
from tools.five_whys_tool import FiveWhysTool
from tools.fishbone_tool import FishboneTool

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
        
        # Initialize Fishbone tool
        self.fishbone = FishboneTool(llm_adapter, rag_manager)
        
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
        image_path = kwargs.get("image_path")    # optional: absolute path to image file
        image_desc = kwargs.get("image_desc")    # optional: user description of image
        
        async def _send_status(msg: str):
            if status_callback:
                await status_callback(msg)
        
        async def _analyze_image_async():
            """Run image analysis in a thread (it uses synchronous requests)."""
            if not image_path:
                return None
            try:
                from tools.image_analysis_tool import analyze_image
                await _send_status("📷 Analyzing uploaded equipment image...")
                result = await asyncio.to_thread(analyze_image, image_path, image_desc)
                await _send_status(
                    f"✓ Image analyzed — {result.get('component', '?')}: "
                    f"{result.get('damage_type', '?')} ({result.get('severity', '?')})"
                )
                return result
            except Exception as e:
                logger.error(f"Image analysis failed: {e}", exc_info=True)
                await _send_status(f"⚠ Image analysis failed: {e}")
                return None

        async def _perform_analysis():
            # Step 1: Route to domain agents
            await _send_status("🔍 Routing to domain experts...")
            selected_agents = self._route_agents(failure_description, symptoms)
            await _send_status(f"✓ Selected experts: {', '.join([a.replace('_agent', '').title() for a in selected_agents])}")
            
            # Step 2: Run domain agents AND image analysis in PARALLEL
            await _send_status("🔬 Domain experts + Image analysis running in parallel...")
            domain_results, image_analysis = await asyncio.gather(
                self._run_domain_agents(
                    selected_agents,
                    failure_description,
                    equipment_name,
                    symptoms,
                    status_callback
                ),
                _analyze_image_async(),
            )
            
            # Step 3: Aggregate domain insights
            await _send_status("📊 Aggregating domain expert insights...")
            domain_insights = self._aggregate_domain_insights(domain_results)
            await _send_status(
                f"✓ Domain analysis complete — {len(domain_insights.key_findings)} "
                f"key findings identified (avg confidence: {domain_insights.overall_confidence*100:.0f}%)"
            )
            
            # ── Emit domain insights immediately as a special event ──────────
            if status_callback:
                await status_callback(("__DOMAIN_INSIGHTS__", domain_insights.model_dump(mode='json')))

            # ── Emit image analysis immediately as a special event ────────────
            if image_analysis and status_callback:
                await status_callback(("__IMAGE_ANALYSIS__", image_analysis))

            
            # Step 4: Run enhanced 5 Whys
            await _send_status("🎯 Starting main root cause analysis (5 Whys)...")
            await _send_status("Using domain expert insights as foundation...")

            
            five_whys_result = await self.five_whys.analyze(
                failure_description=failure_description,
                equipment_name=equipment_name,
                symptoms=symptoms,
                domain_insights=domain_insights,  # Pass domain context
                image_analysis=image_analysis,     # Pass image analysis context
                status_callback=status_callback
            )
            
            # Step 5: Run Fishbone analysis using confirmed root cause
            root_cause = five_whys_result.result.get("root_cause", failure_description)
            fishbone_result = await self.fishbone.analyze(
                failure_description=failure_description,
                equipment_name=equipment_name,
                symptoms=symptoms,
                root_cause=root_cause,
                domain_insights=domain_insights,
                status_callback=status_callback
            )
            
            # Step 6: Build comprehensive result
            fishbone_data = None
            if fishbone_result.success:
                fishbone_data = fishbone_result.result
            else:
                logger.error(
                    f"Fishbone analysis failed: {fishbone_result.error}"
                )

            result_dict = {
                "domain_insights": domain_insights.model_dump(),
                "five_whys_analysis": five_whys_result.result,
                "fishbone_analysis": fishbone_data,
                "final_root_cause": root_cause,
                "final_confidence": five_whys_result.result["root_cause_confidence"],
                "analysis_method": "domain_enhanced_5_whys_fishbone",
                "agents_used": selected_agents
            }
            # Include image analysis in result if present
            if image_analysis:
                result_dict["image_analysis"] = image_analysis
            return result_dict
        
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
