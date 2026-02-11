"""
Model Comparison Runner

Compares Azure OpenAI GPT-4 and Google Gemini Pro for RCA analysis.
Tests both models in two scenarios:
1. Without RAG (direct model knowledge)
2. With RAG (using Weaviate knowledge base)
"""

import asyncio
import json
import os
import sys
from typing import Dict, List, Any
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from model_comparison.azure_adapter import AzureOpenAIAdapter
from model_comparison.gemini_adapter import GeminiAdapter
from rag_manager import RAGManager


class ModelComparisonRunner:
    """Runs comparison between Azure OpenAI and Gemini."""
    
    def __init__(self, scenarios_path: str = None):
        """Initialize comparison runner."""
        # Load environment variables
        llm_dir = os.path.dirname(os.path.dirname(__file__))
        env_path = os.path.join(llm_dir, ".env")
        load_dotenv(env_path)
        
        if scenarios_path is None:
            scenarios_path = os.path.join(
                os.path.dirname(__file__),
                "test_scenarios.json"
            )
        
        with open(scenarios_path, "r") as f:
            data = json.load(f)
            self.scenarios = data["scenarios"]
        
        # Initialize models
        print("Initializing models...")
        self.azure_model = AzureOpenAIAdapter()
        self.gemini_model = GeminiAdapter()
        
        # Initialize RAG manager
        print("Initializing RAG manager...")
        self.rag = RAGManager()
        self.rag.connect()
        
        self.results = {
            "azure_no_rag": [],
            "azure_with_rag": [],
            "gemini_no_rag": [],
            "gemini_with_rag": []
        }
    
    async def run_comparison(
        self,
        num_scenarios: int = 2,
        output_dir: str = None
    ):
        """
        Run comparison across scenarios.
        
        Args:
            num_scenarios: Number of scenarios to test (default 2)
            output_dir: Directory to save results (default: model_comparison/results)
        """
        # Default output directory in model_comparison folder
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), "results")
        
        print(f"\n{'='*70}")
        print("MODEL COMPARISON: Azure OpenAI GPT-4.1 vs Google Gemini 3 Flash")
        print(f"{'='*70}\n")
        
        print(f"Testing {num_scenarios} scenarios")
        print(f"Scenarios: Without RAG + With RAG")
        print(f"Output directory: {output_dir}\n")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Test first N scenarios
        test_scenarios = self.scenarios[:num_scenarios]
        
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n{'='*70}")
            print(f"SCENARIO {i}/{num_scenarios}: {scenario['name']}")
            print(f"{'='*70}")
            print(f"Equipment: {scenario['equipment_name']}")
            print(f"Description: {scenario['failure_description'][:100]}...")
            print(f"Symptoms: {len(scenario['symptoms'])} observed\n")
            
            # --- Test 1: Without RAG ---
            print(f"\n--- Test 1: WITHOUT RAG (Direct Model Knowledge) ---\n")
            
            # Azure without RAG
            print("Testing Azure OpenAI GPT-4.1...")
            azure_result_no_rag = self.azure_model.analyze_failure(
                failure_description=scenario["failure_description"],
                equipment_name=scenario["equipment_name"],
                symptoms=scenario["symptoms"],
                use_rag=False
            )
            self.results["azure_no_rag"].append({
                "scenario_id": scenario["id"],
                "scenario_name": scenario["name"],
                **azure_result_no_rag
            })
            print(f"  ✓ Completed in {azure_result_no_rag['response_time_seconds']:.2f}s")
            print(f"  Cost: ${azure_result_no_rag['cost_usd']:.4f}")
            print(f"  Root cause: {azure_result_no_rag['root_cause'][:80]}...")
            
            # Gemini without RAG
            print("\nTesting Google Gemini Pro...")
            gemini_result_no_rag = self.gemini_model.analyze_failure(
                failure_description=scenario["failure_description"],
                equipment_name=scenario["equipment_name"],
                symptoms=scenario["symptoms"],
                use_rag=False
            )
            self.results["gemini_no_rag"].append({
                "scenario_id": scenario["id"],
                "scenario_name": scenario["name"],
                **gemini_result_no_rag
            })
            print(f"  ✓ Completed in {gemini_result_no_rag['response_time_seconds']:.2f}s")
            print(f"  Cost: ${gemini_result_no_rag['cost_usd']:.4f}")
            print(f"  Root cause: {gemini_result_no_rag['root_cause'][:80]}...")
            
            # --- Test 2: With RAG ---
            print(f"\n--- Test 2: WITH RAG (Using Weaviate Knowledge Base) ---\n")
            
            # Retrieve relevant context from RAG
            print("Retrieving relevant documentation from Weaviate...")
            rag_docs = await self.rag.retrieve_equipment_context(
                equipment_name=scenario["equipment_name"],
                failure_symptoms=scenario["symptoms"],
                top_k=5
            )
            
            if rag_docs:
                context = "\n\n".join([
                    f"[Document {i+1} - Score: {doc.score:.3f}]\n{doc.content}"
                    for i, doc in enumerate(rag_docs)
                ])
                print(f"  ✓ Retrieved {len(rag_docs)} relevant documents")
            else:
                context = "No relevant documentation found."
                print(f"  ⚠ No documents retrieved")
            
            # Azure with RAG
            print("\nTesting Azure OpenAI GPT-4.1 with RAG...")
            azure_result_rag = self.azure_model.analyze_failure(
                failure_description=scenario["failure_description"],
                equipment_name=scenario["equipment_name"],
                symptoms=scenario["symptoms"],
                context=context,
                use_rag=True
            )
            self.results["azure_with_rag"].append({
                "scenario_id": scenario["id"],
                "scenario_name": scenario["name"],
                "rag_docs_retrieved": len(rag_docs),
                **azure_result_rag
            })
            print(f"  ✓ Completed in {azure_result_rag['response_time_seconds']:.2f}s")
            print(f"  Cost: ${azure_result_rag['cost_usd']:.4f}")
            print(f"  Root cause: {azure_result_rag['root_cause'][:80]}...")
            
            # Gemini with RAG
            print("\nTesting Google Gemini Pro with RAG...")
            gemini_result_rag = self.gemini_model.analyze_failure(
                failure_description=scenario["failure_description"],
                equipment_name=scenario["equipment_name"],
                symptoms=scenario["symptoms"],
                context=context,
                use_rag=True
            )
            self.results["gemini_with_rag"].append({
                "scenario_id": scenario["id"],
                "scenario_name": scenario["name"],
                "rag_docs_retrieved": len(rag_docs),
                **gemini_result_rag
            })
            print(f"  ✓ Completed in {gemini_result_rag['response_time_seconds']:.2f}s")
            print(f"  Cost: ${gemini_result_rag['cost_usd']:.4f}")
            print(f"  Root cause: {gemini_result_rag['root_cause'][:80]}...")
        
        # Save results
        self._save_results(output_dir)
        
        # Generate report
        self._generate_report(output_dir)
        
        # Cleanup
        self.rag.disconnect()
        
        print(f"\n{'='*70}")
        print("COMPARISON COMPLETE")
        print(f"{'='*70}")
        print(f"\nResults saved to: {output_dir}/")
        print(f"  - comparison_report.md (Summary report)")
        print(f"  - azure_no_rag.json (Azure without RAG)")
        print(f"  - azure_with_rag.json (Azure with RAG)")
        print(f"  - gemini_no_rag.json (Gemini without RAG)")
        print(f"  - gemini_with_rag.json (Gemini with RAG)")
    
    def _save_results(self, output_dir: str):
        """Save results to JSON files."""
        for key, results in self.results.items():
            output_file = os.path.join(output_dir, f"{key}.json")
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
    
    def _generate_report(self, output_dir: str):
        """Generate markdown comparison report."""
        report_path = os.path.join(output_dir, "comparison_report.md")
        
        # Calculate statistics
        azure_stats = self.azure_model.get_stats()
        gemini_stats = self.gemini_model.get_stats()
        
        with open(report_path, "w") as f:
            f.write("# AI Model Comparison Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Models Tested:**\n")
            f.write(f"- Azure OpenAI GPT-4.1\n")
            f.write(f"- Google Gemini 3 Flash\n\n")
            f.write(f"**Scenarios:** {len(self.results['azure_no_rag'])}\n\n")
            f.write("---\n\n")
            
            # Summary table
            f.write("## Summary Comparison\n\n")
            f.write("| Model | Scenario | Avg Response Time | Avg Cost | Total Cost |\n")
            f.write("|-------|----------|-------------------|----------|------------|\n")
            
            # Calculate averages
            for model_key, model_name in [
                ("azure_no_rag", "Azure (No RAG)"),
                ("azure_with_rag", "Azure (With RAG)"),
                ("gemini_no_rag", "Gemini (No RAG)"),
                ("gemini_with_rag", "Gemini (With RAG)")
            ]:
                results = self.results[model_key]
                if results:
                    avg_time = sum(r['response_time_seconds'] for r in results) / len(results)
                    avg_cost = sum(r['cost_usd'] for r in results) / len(results)
                    total_cost = sum(r['cost_usd'] for r in results)
                    f.write(f"| {model_name} | All | {avg_time:.2f}s | ${avg_cost:.4f} | ${total_cost:.4f} |\n")
            
            f.write("\n---\n\n")
            
            # Detailed results per scenario
            f.write("## Detailed Results\n\n")
            
            for i, scenario_id in enumerate([r['scenario_id'] for r in self.results['azure_no_rag']], 1):
                scenario = next(s for s in self.scenarios if s['id'] == scenario_id)
                
                f.write(f"### Scenario {i}: {scenario['name']}\n\n")
                f.write(f"**Equipment:** {scenario['equipment_name']}  \n")
                f.write(f"**Description:** {scenario['failure_description']}\n\n")
                
                # Get results for this scenario
                azure_no_rag = next(r for r in self.results['azure_no_rag'] if r['scenario_id'] == scenario_id)
                azure_with_rag = next(r for r in self.results['azure_with_rag'] if r['scenario_id'] == scenario_id)
                gemini_no_rag = next(r for r in self.results['gemini_no_rag'] if r['scenario_id'] == scenario_id)
                gemini_with_rag = next(r for r in self.results['gemini_with_rag'] if r['scenario_id'] == scenario_id)
                
                f.write("#### Azure OpenAI GPT-4.1 (Without RAG)\n")
                f.write(f"- **Root Cause:** {azure_no_rag['root_cause']}\n")
                f.write(f"- **Response Time:** {azure_no_rag['response_time_seconds']:.2f}s\n")
                f.write(f"- **Cost:** ${azure_no_rag['cost_usd']:.4f}\n\n")
                
                f.write("#### Azure OpenAI GPT-4.1 (With RAG)\n")
                f.write(f"- **Root Cause:** {azure_with_rag['root_cause']}\n")
                f.write(f"- **RAG Docs Retrieved:** {azure_with_rag.get('rag_docs_retrieved', 0)}\n")
                f.write(f"- **Response Time:** {azure_with_rag['response_time_seconds']:.2f}s\n")
                f.write(f"- **Cost:** ${azure_with_rag['cost_usd']:.4f}\n\n")
                
                f.write("#### Google Gemini Pro (Without RAG)\n")
                f.write(f"- **Root Cause:** {gemini_no_rag['root_cause']}\n")
                f.write(f"- **Response Time:** {gemini_no_rag['response_time_seconds']:.2f}s\n")
                f.write(f"- **Cost:** ${gemini_no_rag['cost_usd']:.4f}\n\n")
                
                f.write("#### Google Gemini Pro (With RAG)\n")
                f.write(f"- **Root Cause:** {gemini_with_rag['root_cause']}\n")
                f.write(f"- **RAG Docs Retrieved:** {gemini_with_rag.get('rag_docs_retrieved', 0)}\n")
                f.write(f"- **Response Time:** {gemini_with_rag['response_time_seconds']:.2f}s\n")
                f.write(f"- **Cost:** ${gemini_with_rag['cost_usd']:.4f}\n\n")
                
                f.write("---\n\n")
            
            # Recommendation
            f.write("## Recommendation\n\n")
            
            # Simple cost comparison
            azure_total = azure_stats['total_cost_usd']
            gemini_total = gemini_stats['total_cost_usd']
            
            if gemini_total < azure_total:
                savings = ((azure_total - gemini_total) / azure_total) * 100
                f.write(f"**Recommended Model:** Google Gemini 3 Flash\n\n")
                f.write(f"- **Cost Savings:** {savings:.1f}% cheaper than Azure OpenAI\n")
                f.write(f"- **Total Cost:** ${gemini_total:.4f} vs ${azure_total:.4f}\n")
            else:
                f.write(f"**Recommended Model:** Azure OpenAI GPT-4.1\n\n")
                f.write(f"- **Total Cost:** ${azure_total:.4f} vs ${gemini_total:.4f}\n")
            
            f.write("\n---\n\n")
            f.write("## Next Steps\n\n")
            f.write("1. Review detailed results in JSON files\n")
            f.write("2. Evaluate quality of responses for your use case\n")
            f.write("3. Consider cost vs quality trade-offs\n")
            f.write("4. Purchase API credits for chosen model\n")
            f.write("5. Proceed with Phase 2 implementation\n")


async def main():
    """Main entry point."""
    print("\n" + "="*70)
    print("AI MODEL COMPARISON FOR RCA SYSTEM")
    print("="*70 + "\n")
    
    runner = ModelComparisonRunner()
    
    # Run comparison on 2 scenarios (can be changed)
    await runner.run_comparison(num_scenarios=2)


if __name__ == "__main__":
    asyncio.run(main())
