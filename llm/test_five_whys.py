"""
Comprehensive 5 Whys Analysis Tool Test

Tests the 5 Whys tool with multiple scenarios and saves detailed results.
"""

import asyncio
import sys
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from tools.five_whys_tool import FiveWhysTool
from tools.tool_registry import ToolRegistry
from model_comparison.gemini_adapter import GeminiAdapter
from rag_manager import RAGManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_five_whys():
    """Test 5 Whys tool with multiple scenarios and save results."""
    
    print("="*70)
    print("5 WHYS ANALYSIS TOOL - COMPREHENSIVE TEST")
    print("="*70)
    
    # Initialize components
    print("\n1. Initializing components...")
    
    # Initialize Gemini adapter
    gemini = GeminiAdapter()
    print("   ✓ Gemini adapter initialized")
    
    # Initialize RAG manager
    rag = RAGManager()
    rag.connect()
    print("   ✓ RAG manager connected")
    
    # Initialize 5 Whys tool
    five_whys = FiveWhysTool(llm_adapter=gemini, rag_manager=rag)
    print("   ✓ 5 Whys tool initialized")
    
    # Initialize tool registry
    registry = ToolRegistry()
    registry.register_tool("5_whys", five_whys)
    print("   ✓ Tool registry initialized")
    print(f"   Registered tools: {registry.list_tools()}")
    
    # Load test scenarios
    print("\n2. Loading test scenarios...")
    scenarios_path = os.path.join(
        os.path.dirname(__file__),
        "model_comparison",
        # "test_scenarios.json",
        "test_scenarios_extended.json"
    )
    
    with open(scenarios_path, 'r') as f:
        scenarios_data = json.load(f)
    
    # Test with first 2 scenarios
    scenarios = scenarios_data['scenarios'][:2]
    print(f"   ✓ Loaded {len(scenarios)} test scenario(s)")
    
    # Run analysis
    results = []
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'='*70}")
        print(f"SCENARIO {i}/{len(scenarios)}: {scenario['name']}")
        print(f"{'='*70}")
        print(f"Equipment: {scenario['equipment_name']}")
        print(f"Description: {scenario['failure_description'][:80]}...")
        print(f"Symptoms: {len(scenario['symptoms'])} observed\n")
        
        # Execute 5 Whys analysis
        print("Executing 5 Whys analysis...")
        
        try:
            result = await registry.execute_tool(
                name="5_whys",
                failure_description=scenario['failure_description'],
                equipment_name=scenario['equipment_name'],
                symptoms=scenario['symptoms']
            )
            
            # Display results
            if result.success:
                print(f"\n✓ Analysis completed successfully!")
                print(f"  Execution time: {result.execution_time_seconds:.2f}s")
                print(f"  Tokens used: {result.tokens_used}")
                print(f"  Cost: ${result.cost_usd:.4f}")
                
                analysis = result.result
                
                # Display 5 Why steps (summary)
                print(f"\n--- 5 Why Steps (Summary) ---")
                for step in analysis['why_steps']:
                    print(f"\nWhy #{step['step_number']}: {step['question'][:80]}...")
                    print(f"  Answer: {step['answer'][:150]}...")
                    if step['supporting_documents']:
                        print(f"  Documents: {', '.join(step['supporting_documents'][:2])}...")
                    print(f"  Confidence: {step['confidence']*100:.0f}%")
                
                # Display root cause
                print(f"\n--- Root Cause ---")
                print(f"{analysis['root_cause'][:200]}...")
                print(f"Confidence: {analysis['root_cause_confidence']*100:.0f}%")
                
                # Display corrective actions
                print(f"\n--- Corrective Actions ---")
                if analysis['corrective_actions']:
                    for i, action in enumerate(analysis['corrective_actions'], 1):
                        print(f"{i}. {action[:80]}...")
                else:
                    print("(None - corrective actions disabled)")
                
                # Display documents used
                print(f"\n--- Documents Referenced ---")
                unique_docs = list(set(analysis['documents_used']))
                for doc in unique_docs[:5]:
                    print(f"  - {doc}")
                if len(unique_docs) > 5:
                    print(f"  ... and {len(unique_docs) - 5} more")
                
                # Store result
                results.append({
                    'scenario_id': scenario.get('id', f'scenario_{i}'),
                    'scenario_name': scenario['name'],
                    'equipment_name': scenario['equipment_name'],
                    'success': True,
                    'execution_time_seconds': result.execution_time_seconds,
                    'tokens_used': result.tokens_used,
                    'cost_usd': result.cost_usd,
                    'analysis': analysis
                })
            
            else:
                print(f"\n✗ Analysis failed!")
                print(f"  Error: {result.error}")
                
                results.append({
                    'scenario_id': scenario.get('id', f'scenario_{i}'),
                    'scenario_name': scenario['name'],
                    'equipment_name': scenario['equipment_name'],
                    'success': False,
                    'error': result.error,
                    'execution_time_seconds': result.execution_time_seconds
                })
        
        except Exception as e:
            print(f"\n✗ Exception occurred: {e}")
            import traceback
            traceback.print_exc()
            
            results.append({
                'scenario_id': scenario.get('id', f'scenario_{i}'),
                'scenario_name': scenario['name'],
                'equipment_name': scenario['equipment_name'],
                'success': False,
                'error': str(e)
            })
    
    # Save results
    print(f"\n{'='*70}")
    print("SAVING RESULTS")
    print(f"{'='*70}")
    
    output_dir = os.path.join(os.path.dirname(__file__), "test_results")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save detailed JSON results
    json_file = os.path.join(output_dir, f"five_whys_test_{timestamp}.json")
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"✓ Detailed results saved to: {json_file}")
    
    # Save summary report
    summary_file = os.path.join(output_dir, f"five_whys_summary_{timestamp}.md")
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(f"# 5 Whys Analysis Test Summary\n\n")
        f.write(f"**Test Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Scenarios Tested**: {len(results)}\n\n")
        
        # Overall stats
        successful = sum(1 for r in results if r['success'])
        total_time = sum(r.get('execution_time_seconds', 0) for r in results)
        total_cost = sum(r.get('cost_usd', 0) for r in results)
        
        f.write(f"## Overall Statistics\n\n")
        f.write(f"- **Success Rate**: {successful}/{len(results)} ({successful/len(results)*100:.0f}%)\n")
        f.write(f"- **Total Execution Time**: {total_time:.2f}s\n")
        f.write(f"- **Total Cost**: ${total_cost:.4f}\n\n")
        
        # Individual results
        f.write(f"## Individual Results\n\n")
        for i, result in enumerate(results, 1):
            f.write(f"### {i}. {result['scenario_name']}\n\n")
            f.write(f"**Equipment**: {result['equipment_name']}\n\n")
            
            if result['success']:
                f.write(f"**Status**: ✅ Success\n\n")
                f.write(f"**Metrics**:\n")
                f.write(f"- Execution Time: {result['execution_time_seconds']:.2f}s\n")
                f.write(f"- Tokens Used: {result.get('tokens_used', 0)}\n")
                f.write(f"- Cost: ${result.get('cost_usd', 0):.4f}\n\n")
                
                analysis = result['analysis']
                
                # Root cause
                f.write(f"**Root Cause** (Confidence: {analysis['root_cause_confidence']*100:.0f}%):\n\n")
                f.write(f"{analysis['root_cause'][:300]}...\n\n")
                
                # Documents
                unique_docs = list(set(analysis['documents_used']))
                f.write(f"**Documents Referenced** ({len(unique_docs)}):\n\n")
                for doc in unique_docs[:5]:
                    f.write(f"- {doc}\n")
                if len(unique_docs) > 5:
                    f.write(f"- ... and {len(unique_docs) - 5} more\n")
                f.write("\n")
            else:
                f.write(f"**Status**: ❌ Failed\n\n")
                f.write(f"**Error**: {result.get('error', 'Unknown error')}\n\n")
            
            f.write("---\n\n")
    
    print(f"✓ Summary report saved to: {summary_file}")
    
    # Cleanup
    rag.disconnect()
    
    print(f"\n{'='*70}")
    print("TEST COMPLETE")
    print(f"{'='*70}")
    print(f"\nResults saved to:")
    print(f"  - JSON: {json_file}")
    print(f"  - Summary: {summary_file}")


if __name__ == "__main__":
    asyncio.run(test_five_whys())
