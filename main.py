#!/usr/bin/env python3
"""
NetSuite Financial Analyst Agent - Main Entry Point

Usage:
    python main.py slack          # Start Slack bot
    python main.py analyze "query"  # Run one-off analysis
    python main.py test           # Run evaluation tests
    python main.py setup          # Validate configuration
"""
import os
import sys
import argparse
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('agent.log'),
    ]
)
logger = logging.getLogger(__name__)

def setup_environment():
    """Load environment variables from .env file if present."""
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        logger.info("Loading environment from .env file")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

def cmd_slack(args):
    """Start the Slack bot."""
    from src.integrations.slack_bot import create_slack_bot
    
    logger.info("Starting Slack bot...")
    bot = create_slack_bot()
    bot.start()

def cmd_analyze(args):
    """Run a one-off analysis."""
    import asyncio
    from src.agents.financial_analyst import get_financial_analyst
    
    query = args.query
    logger.info(f"Running analysis: {query}")
    
    agent = get_financial_analyst()
    response = asyncio.run(agent.analyze(
        query=query,
        include_charts=args.charts,
        max_iterations=args.iterations,
    ))
    
    # Print results
    print("\n" + "="*60)
    print("ANALYSIS RESULTS")
    print("="*60)
    print(response.analysis)
    print("\n" + "-"*60)
    print("METRICS")
    print("-"*60)
    for calc in response.calculations[:10]:
        print(f"  {calc['metric_name']}: {calc['formatted_value']}")
    
    if response.charts:
        print("\n" + "-"*60)
        print("GENERATED CHARTS")
        print("-"*60)
        for chart in response.charts:
            print(f"  {chart.title}: {chart.file_path}")
    
    print("\n" + "-"*60)
    print("EVALUATION")
    print("-"*60)
    eval_summary = response.evaluation_summary
    print(f"  Passes Threshold: {eval_summary.get('passes_threshold')}")
    print(f"  Qualitative Score: {eval_summary.get('qualitative_score')}/10")
    if eval_summary.get('suggestions'):
        print("  Suggestions:")
        for s in eval_summary['suggestions'][:3]:
            print(f"    - {s}")

def cmd_test(args):
    """Run evaluation tests."""
    from src.evaluation.evaluator import get_evaluation_harness
    
    logger.info("Running evaluation tests...")
    
    # This would run against a Golden Dataset in production
    # For now, just validate the evaluation system works
    harness = get_evaluation_harness()
    
    test_analysis = """
    ## Executive Summary
    Revenue increased by 15% to $1.2M this quarter, driven primarily by 
    the Enterprise segment which grew 25%.
    
    ## Key Findings
    - Total revenue: $1,234,567
    - Enterprise: $750,000 (61%)
    - SMB: $484,567 (39%)
    
    ## Recommendations
    1. Expand Enterprise sales team
    2. Investigate SMB churn
    """
    
    qual_scores, avg_score, suggestions = harness.qualitative_evaluator.evaluate(
        analysis=test_analysis,
        data_summary="Test data with revenue breakdown"
    )
    
    print("\n" + "="*60)
    print("EVALUATION TEST RESULTS")
    print("="*60)
    for score in qual_scores:
        print(f"  {score.dimension.value}: {score.score}/10")
    print(f"\n  Average Score: {avg_score:.1f}/10")
    print(f"  Suggestions: {suggestions[:3]}")

def cmd_refresh_registry(args):
    """Refresh the dynamic semantic registry from NetSuite data."""
    try:
        from src.core.dynamic_registry import get_dynamic_registry
        from src.tools.netsuite_client import get_data_retriever
        
        logger.info("Fetching data from NetSuite to refresh registry...")
        logger.info("(This may take several minutes for large datasets)")
        
        retriever = get_data_retriever(update_registry=False)  # Don't auto-update during refresh
        result = retriever.get_saved_search_data()
        
        logger.info(f"Retrieved {len(result.data):,} rows")
        logger.info("Building dynamic registry...")
        
        registry = get_dynamic_registry()
        registry.build_from_data(result.data, force_rebuild=args.force if hasattr(args, 'force') else False)
        
        print("\n" + "="*60)
        print("REGISTRY STATISTICS")
        print("="*60)
        stats = registry.stats
        print(f"  Departments:       {stats['departments']:,}")
        print(f"  Accounts:          {stats['accounts']:,}")
        print(f"  Account Numbers:   {stats['account_numbers']:,}")
        print(f"  Subsidiaries:      {stats['subsidiaries']:,}")
        print(f"  Transaction Types: {stats['transaction_types']:,}")
        print(f"  Index Terms:       {stats['index_terms']:,}")
        print(f"  Source Rows:       {stats['source_rows']:,}")
        print(f"  Built At:          {stats['built_at']}")
        print(f"  Cache Valid:       {stats['cache_valid']}")
        print("\nRegistry refresh complete!")
        
    except ImportError:
        logger.error("Dynamic registry not available. Ensure src/core/dynamic_registry.py exists.")
    except Exception as e:
        logger.error(f"Failed to refresh registry: {e}")
        import traceback
        traceback.print_exc()


def cmd_registry_stats(args):
    """Show dynamic registry statistics."""
    try:
        from src.core.dynamic_registry import get_dynamic_registry
        
        registry = get_dynamic_registry()
        stats = registry.stats
        
        print("\n" + "="*60)
        print("DYNAMIC REGISTRY STATISTICS")
        print("="*60)
        print(f"  Departments:       {stats['departments']:,}")
        print(f"  Accounts:          {stats['accounts']:,}")
        print(f"  Account Numbers:   {stats['account_numbers']:,}")
        print(f"  Subsidiaries:      {stats['subsidiaries']:,}")
        print(f"  Transaction Types: {stats['transaction_types']:,}")
        print(f"  Index Terms:       {stats['index_terms']:,}")
        print(f"  Source Rows:       {stats['source_rows']:,}")
        print(f"  Built At:          {stats['built_at']}")
        print(f"  Cache Valid:       {stats['cache_valid']}")
        print("="*60)
        
        if registry.is_empty():
            print("\nRegistry is empty. Run 'python main.py refresh-registry' to build it.")
        elif registry.needs_refresh():
            print("\nRegistry needs refresh. Run 'python main.py refresh-registry' to update it.")
        else:
            print("\nRegistry is up to date.")
            
    except ImportError:
        logger.error("Dynamic registry not available. Ensure src/core/dynamic_registry.py exists.")
    except Exception as e:
        logger.error(f"Error getting registry stats: {e}", exc_info=True)
        print(f"\nError: {e}")


def cmd_traces(args):
    """View and analyze traces."""
    from pathlib import Path
    import json
    from datetime import datetime
    
    traces_dir = Path(os.getenv("TRACE_EXPORT_DIR", "traces"))
    
    if args.list:
        # List recent traces
        traces = sorted(traces_dir.glob("trace_*.json"), reverse=True)[:args.limit]
        
        print("\n" + "=" * 80)
        print("RECENT TRACES")
        print("=" * 80)
        print(f"{'Trace ID':<40} {'Duration':<12} {'Cost':<10} {'Status':<8}")
        print("-" * 80)
        
        for trace_file in traces:
            try:
                with open(trace_file) as f:
                    trace = json.load(f)
                print(
                    f"{trace['trace_id']:<40} "
                    f"{trace['duration_ms']:.0f}ms{'':<6} "
                    f"${trace['metrics']['estimated_cost_usd']:.4f}{'':<4} "
                    f"{trace['status']}"
                )
            except Exception as e:
                print(f"{trace_file.name}: Error reading trace - {e}")
    
    elif args.view:
        # View specific trace
        trace_file = traces_dir / f"{args.view}.json"
        if not trace_file.exists():
            print(f"Trace not found: {args.view}")
            return
        
        with open(trace_file) as f:
            trace = json.load(f)
        
        print("\n" + "=" * 80)
        print(f"TRACE: {trace['trace_id']}")
        print("=" * 80)
        print(f"Query: {trace['query']}")
        print(f"Duration: {trace['duration_ms']:.0f}ms")
        print(f"Status: {trace['status']}")
        print(f"\nMetrics:")
        for key, value in trace['metrics'].items():
            print(f"  {key}: {value}")
        
        print(f"\nSpans ({len(trace['spans'])}):")
        for span in trace['spans']:
            indent = "  " if span.get('parent_span_id') else ""
            print(f"{indent}- {span['name']}: {span['duration_ms']:.0f}ms [{span['status']}]")
            if span.get('llm_usage'):
                usage = span['llm_usage']
                print(f"{indent}  LLM: {usage['model']} ({usage['total_tokens']} tokens, ${usage['estimated_cost_usd']:.4f})")
    
    elif args.stats:
        # Show aggregate statistics
        traces = list(traces_dir.glob("trace_*.json"))
        
        if not traces:
            print("No traces found.")
            return
        
        total_cost = 0
        total_duration = 0
        total_tokens = 0
        success_count = 0
        
        for trace_file in traces:
            try:
                with open(trace_file) as f:
                    trace = json.load(f)
                total_cost += trace['metrics']['estimated_cost_usd']
                total_duration += trace['duration_ms']
                total_tokens += trace['metrics']['total_tokens']
                if trace['status'] == 'ok':
                    success_count += 1
            except Exception:
                continue
        
        print("\n" + "=" * 60)
        print("TRACE STATISTICS")
        print("=" * 60)
        print(f"Total Traces: {len(traces)}")
        print(f"Success Rate: {success_count/len(traces)*100:.1f}%")
        print(f"Total Cost: ${total_cost:.4f}")
        print(f"Avg Cost/Query: ${total_cost/len(traces):.4f}")
        print(f"Total Tokens: {total_tokens:,}")
        print(f"Avg Duration: {total_duration/len(traces):.0f}ms")

def cmd_regression(args):
    """Run regression tests against a golden dataset."""
    import asyncio
    import json
    import sys
    from pathlib import Path
    from datetime import datetime
    from tests.golden_dataset import GoldenDataset, run_regression_suite
    from src.agents.financial_analyst import get_financial_analyst
    
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        return
    
    logger.info(f"Loading golden dataset from {dataset_path}")
    dataset = GoldenDataset.load(dataset_path)
    
    logger.info(f"Loaded {len(dataset.test_cases)} test cases")
    
    agent = get_financial_analyst()
    
    report = asyncio.run(run_regression_suite(
        agent=agent,
        dataset=dataset,
        parallel=args.parallel,
    ))
    
    # Print summary
    report.print_summary()
    
    # Save detailed results
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path("regression_results") / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(report.to_dict(), f, indent=2)
    
    print(f"\nDetailed results saved to: {output_path}")
    
    # Exit with error code if tests failed
    if report.failed > 0 or report.errors > 0:
        sys.exit(1)

def cmd_prompts(args):
    """Manage prompts."""
    from src.core.prompt_manager import get_prompt_manager
    
    pm = get_prompt_manager()
    
    if args.action == 'list':
        prompts = pm.list_prompts()
        active = pm.get_active_versions()
        
        print("\n" + "=" * 60)
        print("AVAILABLE PROMPTS")
        print("=" * 60)
        
        for name, versions in sorted(prompts.items()):
            active_version = active.get(name, versions[-1] if versions else "N/A")
            print(f"\n{name}:")
            for v in versions:
                marker = " (active)" if v == active_version else ""
                print(f"  - v{v}{marker}")
    
    elif args.action == 'show':
        try:
            prompt = pm.get_prompt(args.name, getattr(args, 'version', None))
            
            print("\n" + "=" * 60)
            print(f"PROMPT: {prompt.name} v{prompt.version}")
            print("=" * 60)
            print(f"Description: {prompt.description}")
            print(f"Hash: {prompt.hash}")
            print(f"Created: {prompt.created_at}")
            print(f"\nSystem Prompt:\n{'-' * 40}")
            print(prompt.system_prompt[:500] + "..." if len(prompt.system_prompt) > 500 else prompt.system_prompt)
            print(f"\nUser Template:\n{'-' * 40}")
            print(prompt.user_prompt_template[:500] + "..." if len(prompt.user_prompt_template) > 500 else prompt.user_prompt_template)
            print(f"\nRequired Variables: {prompt.required_variables}")
            print(f"Optional Variables: {list(prompt.optional_variables.keys())}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
    
    elif args.action == 'set-active':
        try:
            pm.set_active_version(args.name, args.version)
            print(f"Set active version for '{args.name}' to v{args.version}")
        except FileNotFoundError as e:
            print(f"Error: {e}")

def cmd_setup(args):
    """Validate configuration and setup."""
    from config.settings import get_config, MODEL_REGISTRY
    
    print("\n" + "="*60)
    print("CONFIGURATION VALIDATION")
    print("="*60)
    
    config = get_config()
    
    # Check active model
    print(f"\n[Model] Active Model: {config.active_model}")
    try:
        model_config = config.model_config
        print(f"   Provider: {model_config.provider.value}")
        print(f"   Model: {model_config.model_name}")
        
        # Check API key
        api_key_var = model_config.api_key_env
        has_key = bool(os.getenv(api_key_var))
        status = "[OK]" if has_key else "[MISSING]"
        print(f"   {status} API Key ({api_key_var}): {'Set' if has_key else 'MISSING'}")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Check NetSuite config
    print(f"\n[NetSuite] Configuration:")
    ns = config.netsuite
    checks = [
        ("Account ID", ns.account_id),
        ("Consumer Key", ns.consumer_key),
        ("Saved Search ID", ns.saved_search_id),
    ]
    for name, value in checks:
        status = "[OK]" if value else "[MISSING]"
        print(f"   {status} {name}: {'Set' if value else 'MISSING'}")
    
    # Check Fiscal config
    print(f"\n[Fiscal] Calendar Configuration:")
    print(f"   Fiscal Year Start Month: {config.fiscal.fiscal_year_start_month}")
    
    # Check Slack config
    print(f"\n[Slack] Configuration:")
    slack = config.slack
    checks = [
        ("Bot Token", slack.bot_token),
        ("Signing Secret", slack.signing_secret),
        ("App Token", slack.app_token),
    ]
    for name, value in checks:
        status = "[OK]" if value else "[MISSING]"
        print(f"   {status} {name}: {'Set' if value else 'MISSING'}")
    
    # Available models
    print(f"\n[Models] Available Models:")
    for name in MODEL_REGISTRY:
        marker = "->" if name == config.active_model else "  "
        print(f"   {marker} {name}")
    
    print("\n" + "="*60)
    print("To switch models, set: ACTIVE_MODEL=<model-name>")
    print("="*60)

def cmd_interactive(args):
    """Start interactive chat mode with conversation memory."""
    import asyncio
    from src.agents.financial_analyst import get_financial_analyst
    from src.core.memory import get_session_manager
    
    print("\n" + "="*60)
    print("INTERACTIVE FINANCIAL ANALYST")
    print("="*60)
    print("Ask questions about your NetSuite data.")
    print("The agent remembers context from previous questions.")
    print("Type 'quit' or 'exit' to end, 'clear' to reset context.")
    print("="*60 + "\n")
    
    agent = get_financial_analyst()
    session_manager = get_session_manager()
    session = session_manager.create_session()
    
    while True:
        try:
            query = input("\nYou: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break
            
            if query.lower() == 'clear':
                session = session_manager.create_session()
                print("\n[Context cleared. Starting fresh conversation.]")
                continue
            
            if query.lower() == 'context':
                if session.context.has_context():
                    print(f"\n[Current Context]\n{session.context.to_prompt_context()}")
                else:
                    print("\n[No context accumulated yet.]")
                continue
            
            print("\nAnalyzing... (this may take a moment)")
            
            response = asyncio.run(agent.analyze(
                query=query,
                include_charts=not args.no_charts,
                max_iterations=args.iterations,
                session=session,
            ))
            
            print("\n" + "-"*60)
            print("ANALYSIS")
            print("-"*60)
            print(response.analysis)
            
            if response.calculations:
                print("\n" + "-"*40)
                print("KEY METRICS")
                print("-"*40)
                for calc in response.calculations[:5]:
                    print(f"  {calc['metric_name']}: {calc['formatted_value']}")
            
            if response.charts:
                print(f"\n[{len(response.charts)} chart(s) generated]")
            
            # Show session info
            print(f"\n[Session: {session.session_id[:8]}... | Turns: {len(session.turns)}]")
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            print(f"\n[Error: {e}]")

def main():
    setup_environment()
    
    parser = argparse.ArgumentParser(
        description="NetSuite Financial Analyst Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py slack                    Start the Slack bot
  python main.py analyze "Show revenue"   Run a one-off analysis
  python main.py interactive              Start interactive chat mode
  python main.py setup                    Check configuration
  
Environment Variables:
  ACTIVE_MODEL              LLM to use (default: gemini-2.0-flash)
  GEMINI_API_KEY            Google AI API key
  NETSUITE_SAVED_SEARCH_ID  Your saved search ID
  FISCAL_YEAR_START_MONTH   Fiscal year start month (1-12, default: 2)
  SLACK_BOT_TOKEN           Slack bot token
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Slack command
    slack_parser = subparsers.add_parser('slack', help='Start Slack bot')
    slack_parser.set_defaults(func=cmd_slack)
    
    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Run analysis')
    analyze_parser.add_argument('query', help='Analysis query')
    analyze_parser.add_argument('--no-charts', dest='charts', action='store_false',
                               help='Disable chart generation')
    analyze_parser.add_argument('--iterations', type=int, default=3,
                               help='Max reflection iterations')
    analyze_parser.set_defaults(func=cmd_analyze)
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Run tests')
    test_parser.set_defaults(func=cmd_test)
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Validate setup')
    setup_parser.set_defaults(func=cmd_setup)
    
    # Refresh registry command
    refresh_parser = subparsers.add_parser('refresh-registry', help='Refresh the dynamic semantic registry from NetSuite data')
    refresh_parser.add_argument('--force', action='store_true', help='Force refresh even if cache is valid')
    refresh_parser.set_defaults(func=cmd_refresh_registry)
    
    # Registry stats command
    stats_parser = subparsers.add_parser('registry-stats', help='Show dynamic registry statistics')
    stats_parser.set_defaults(func=cmd_registry_stats)
    
    # Interactive command
    interactive_parser = subparsers.add_parser('interactive', help='Interactive chat mode')
    interactive_parser.add_argument('--no-charts', dest='no_charts', action='store_true',
                                   help='Disable chart generation')
    interactive_parser.add_argument('--iterations', type=int, default=2,
                                   help='Max reflection iterations (default: 2)')
    interactive_parser.set_defaults(func=cmd_interactive)
    
    # Traces command
    traces_parser = subparsers.add_parser('traces', help='View and analyze traces')
    traces_parser.add_argument('--list', action='store_true', help='List recent traces')
    traces_parser.add_argument('--view', type=str, help='View specific trace by ID')
    traces_parser.add_argument('--stats', action='store_true', help='Show aggregate statistics')
    traces_parser.add_argument('--limit', type=int, default=20, help='Number of traces to list')
    traces_parser.set_defaults(func=cmd_traces)
    
    # Regression command
    regression_parser = subparsers.add_parser('regression', help='Run regression tests')
    regression_parser.add_argument('dataset', help='Path to golden dataset JSON file')
    regression_parser.add_argument('--parallel', action='store_true', help='Run tests in parallel')
    regression_parser.add_argument('--output', '-o', help='Output path for detailed results')
    regression_parser.set_defaults(func=cmd_regression)
    
    # Prompts command
    prompts_parser = subparsers.add_parser('prompts', help='Manage prompts')
    prompts_subparsers = prompts_parser.add_subparsers(dest='action')
    
    list_parser = prompts_subparsers.add_parser('list', help='List all prompts')
    list_parser.set_defaults(func=lambda args: cmd_prompts(type('Args', (), {'action': 'list', 'name': None, 'version': None})()))
    
    show_parser = prompts_subparsers.add_parser('show', help='Show a prompt')
    show_parser.add_argument('name', help='Prompt name')
    show_parser.add_argument('--version', '-v', help='Specific version')
    show_parser.set_defaults(func=lambda args: cmd_prompts(type('Args', (), {'action': 'show', 'name': args.name, 'version': getattr(args, 'version', None)})()))
    
    setactive_parser = prompts_subparsers.add_parser('set-active', help='Set active version')
    setactive_parser.add_argument('name', help='Prompt name')
    setactive_parser.add_argument('version', help='Version to activate')
    setactive_parser.set_defaults(func=lambda args: cmd_prompts(type('Args', (), {'action': 'set-active', 'name': args.name, 'version': args.version})()))
    
    def cmd_prompts_wrapper(args):
        """Wrapper for prompts command to handle subparsers."""
        if hasattr(args, 'action'):
            cmd_prompts(args)
        else:
            prompts_parser.print_help()
    
    prompts_parser.set_defaults(func=cmd_prompts_wrapper)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
