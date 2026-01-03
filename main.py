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
