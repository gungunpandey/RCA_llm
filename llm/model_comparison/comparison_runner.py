"""
Model Comparison Framework - Main Runner

Compares Gemini 3 and GPT-5 for RCA analysis tasks.
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

# Model adapters will be imported when API keys are available
# from .gemini_adapter import GeminiAdapter
# from .gpt_adapter import GPTAdapter


@dataclass
class ModelResult:
    """Result from a single model on a single scenario."""
    model_name: str
    scenario_id: str
    root_cause: str
    reasoning_steps: List[str]
    confidence: float
    response_time_seconds: float
    tokens_used: int
    cost_usd: float
    raw_response: Dict[str, Any]


@dataclass
class ComparisonMetrics:
    """Comparison metrics between models."""
    model_name: str
    avg_quality_score: float
    avg_cost_per_analysis: float
    avg_response_time: float
    total_cost: float
    success_rate: float


class ModelComparisonRunner:
    """
    Runs comparison between different AI models.
    
    Usage:
        runner = ModelComparisonRunner()
        await runner.run_comparison(models=["gemini", "gpt5"])
    """
    
    def __init__(self, scenarios_path: str = None):
        """Initialize comparison runner."""
        if scenarios_path is None:
            scenarios_path = os.path.join(
                os.path.dirname(__file__),
                "test_scenarios.json"
            )
        
        with open(scenarios_path, "r") as f:
            data = json.load(f)
            self.scenarios = data["scenarios"]
        
        self.results: Dict[str, List[ModelResult]] = {}
    
    async def run_comparison(
        self,
        models: List[str],
        output_dir: str = "results"
    ) -> Dict[str, ComparisonMetrics]:
        """
        Run comparison across all scenarios for specified models.
        
        Args:
            models: List of model names (e.g., ["gemini", "gpt5"])
            output_dir: Directory to save results
            
        Returns:
            Dictionary of comparison metrics per model
        """
        print(f"\n{'='*60}")
        print("MODEL COMPARISON FRAMEWORK")
        print(f"{'='*60}\n")
        
        print(f"Models to compare: {', '.join(models)}")
        print(f"Test scenarios: {len(self.scenarios)}")
        print(f"Output directory: {output_dir}\n")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Run each model on each scenario
        for model_name in models:
            print(f"\n--- Testing {model_name.upper()} ---")
            self.results[model_name] = []
            
            for scenario in self.scenarios:
                print(f"\nScenario: {scenario['name']}")
                
                try:
                    result = await self._run_single_test(model_name, scenario)
                    self.results[model_name].append(result)
                    
                    print(f"  ✓ Completed in {result.response_time_seconds:.2f}s")
                    print(f"  Root cause: {result.root_cause[:80]}...")
                    
                except Exception as e:
                    print(f"  ✗ Failed: {e}")
        
        # Calculate metrics
        metrics = self._calculate_metrics()
        
        # Save results
        self._save_results(output_dir, metrics)
        
        # Generate comparison report
        self._generate_report(output_dir, metrics)
        
        return metrics
    
    async def _run_single_test(
        self,
        model_name: str,
        scenario: Dict[str, Any]
    ) -> ModelResult:
        """
        Run a single test scenario on a model.
        
        NOTE: This is a placeholder. Actual implementation requires API keys.
        """
        # TODO: Implement actual model calls when API keys are available
        
        # Placeholder simulation
        await asyncio.sleep(0.5)  # Simulate API call
        
        return ModelResult(
            model_name=model_name,
            scenario_id=scenario["id"],
            root_cause=f"[PLACEHOLDER] {scenario['expected_root_cause']}",
            reasoning_steps=[
                "Step 1: Analyzed symptoms",
                "Step 2: Retrieved relevant documentation",
                "Step 3: Identified root cause"
            ],
            confidence=0.85,
            response_time_seconds=1.2,
            tokens_used=1500,
            cost_usd=0.015,
            raw_response={"placeholder": True}
        )
    
    def _calculate_metrics(self) -> Dict[str, ComparisonMetrics]:
        """Calculate comparison metrics for each model."""
        metrics = {}
        
        for model_name, results in self.results.items():
            if not results:
                continue
            
            metrics[model_name] = ComparisonMetrics(
                model_name=model_name,
                avg_quality_score=sum(r.confidence for r in results) / len(results) * 100,
                avg_cost_per_analysis=sum(r.cost_usd for r in results) / len(results),
                avg_response_time=sum(r.response_time_seconds for r in results) / len(results),
                total_cost=sum(r.cost_usd for r in results),
                success_rate=100.0  # Placeholder
            )
        
        return metrics
    
    def _save_results(self, output_dir: str, metrics: Dict[str, ComparisonMetrics]):
        """Save raw results and metrics to JSON files."""
        # Save raw results
        for model_name, results in self.results.items():
            output_file = os.path.join(output_dir, f"{model_name}_results.json")
            with open(output_file, "w") as f:
                json.dump([asdict(r) for r in results], f, indent=2)
            print(f"\nSaved {model_name} results to: {output_file}")
        
        # Save metrics
        metrics_file = os.path.join(output_dir, "metrics.json")
        with open(metrics_file, "w") as f:
            json.dump({k: asdict(v) for k, v in metrics.items()}, f, indent=2)
        print(f"Saved metrics to: {metrics_file}")
    
    def _generate_report(self, output_dir: str, metrics: Dict[str, ComparisonMetrics]):
        """Generate markdown comparison report."""
        report_path = os.path.join(output_dir, "comparison_report.md")
        
        with open(report_path, "w") as f:
            f.write("# AI Model Comparison Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Scenarios Tested:** {len(self.scenarios)}\n\n")
            f.write("---\n\n")
            
            f.write("## Summary Metrics\n\n")
            f.write("| Model | Avg Quality | Avg Cost | Avg Time | Total Cost | Success Rate |\n")
            f.write("|-------|-------------|----------|----------|------------|-------------|\n")
            
            for model_name, m in metrics.items():
                f.write(f"| {model_name} | {m.avg_quality_score:.1f}% | ${m.avg_cost_per_analysis:.4f} | {m.avg_response_time:.2f}s | ${m.total_cost:.2f} | {m.success_rate:.1f}% |\n")
            
            f.write("\n---\n\n")
            f.write("## Recommendation\n\n")
            
            # Simple recommendation logic
            if len(metrics) >= 2:
                sorted_models = sorted(
                    metrics.items(),
                    key=lambda x: (x[1].avg_quality_score * 0.4 + 
                                  (100 - x[1].avg_cost_per_analysis * 1000) * 0.25 +
                                  (100 - x[1].avg_response_time * 10) * 0.20),
                    reverse=True
                )
                winner = sorted_models[0][0]
                f.write(f"**Recommended Model:** {winner}\n\n")
            
            f.write("\n---\n\n")
            f.write("## Next Steps\n\n")
            f.write("1. Review detailed results in JSON files\n")
            f.write("2. Purchase API credits for chosen model\n")
            f.write("3. Proceed with Phase 2 implementation\n")
        
        print(f"\nGenerated comparison report: {report_path}")


async def main():
    """Main entry point for model comparison."""
    print("\n" + "="*60)
    print("AI MODEL COMPARISON FOR RCA SYSTEM")
    print("="*60 + "\n")
    
    print("⚠️  NOTE: This requires API keys to be configured in .env")
    print("   - GOOGLE_API_KEY for Gemini 3")
    print("   - OPENAI_API_KEY for GPT-5\n")
    
    # Check for API keys
    from dotenv import load_dotenv
    load_dotenv()
    
    has_gemini = bool(os.getenv("GOOGLE_API_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    
    models_to_test = []
    if has_gemini:
        models_to_test.append("gemini")
        print("✓ Gemini API key found")
    else:
        print("✗ Gemini API key not found")
    
    if has_openai:
        models_to_test.append("gpt5")
        print("✓ OpenAI API key found")
    else:
        print("✗ OpenAI API key not found")
    
    if not models_to_test:
        print("\n❌ No API keys configured. Please add to .env file:")
        print("   GOOGLE_API_KEY=your-key-here")
        print("   OPENAI_API_KEY=your-key-here\n")
        return
    
    print(f"\nWill test models: {', '.join(models_to_test)}\n")
    
    # Run comparison
    runner = ModelComparisonRunner()
    metrics = await runner.run_comparison(models=models_to_test)
    
    print("\n" + "="*60)
    print("COMPARISON COMPLETE")
    print("="*60)
    print("\nCheck the 'results/' directory for detailed reports.")


if __name__ == "__main__":
    asyncio.run(main())
