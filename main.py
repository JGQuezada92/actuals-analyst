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

def cmd_setup(args):
    """Validate configuration and setup."""
    from config.settings import get_config, MODEL_REGISTRY
    
    print("\n" + "="*60)
    print("CONFIGURATION VALIDATION")
    print("="*60)
    
    config = get_config()
    
    # Check active model
    print(f"\n📊 Active Model: {config.active_model}")
    try:
        model_config = config.model_config
        print(f"   Provider: {model_config.provider.value}")
        print(f"   Model: {model_config.model_name}")
        
        # Check API key
        api_key_var = model_config.api_key_env
        has_key = bool(os.getenv(api_key_var))
        status = "✅" if has_key else "❌"
        print(f"   {status} API Key ({api_key_var}): {'Set' if has_key else 'MISSING'}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Check NetSuite config
    print(f"\n📦 NetSuite Configuration:")
    ns = config.netsuite
    checks = [
        ("Account ID", ns.account_id),
        ("Consumer Key", ns.consumer_key),
        ("Saved Search ID", ns.saved_search_id),
    ]
    for name, value in checks:
        status = "✅" if value else "❌"
        print(f"   {status} {name}: {'Set' if value else 'MISSING'}")
    
    # Check Slack config
    print(f"\n💬 Slack Configuration:")
    slack = config.slack
    checks = [
        ("Bot Token", slack.bot_token),
        ("Signing Secret", slack.signing_secret),
        ("App Token", slack.app_token),
    ]
    for name, value in checks:
        status = "✅" if value else "❌"
        print(f"   {status} {name}: {'Set' if value else 'MISSING'}")
    
    # Available models
    print(f"\n🤖 Available Models:")
    for name in MODEL_REGISTRY:
        marker = "→" if name == config.active_model else " "
        print(f"   {marker} {name}")
    
    print("\n" + "="*60)
    print("To switch models, set: ACTIVE_MODEL=<model-name>")
    print("="*60)

def main():
    setup_environment()
    
    parser = argparse.ArgumentParser(
        description="NetSuite Financial Analyst Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py slack                    Start the Slack bot
  python main.py analyze "Show revenue"   Run an analysis
  python main.py setup                    Check configuration
  
Environment Variables:
  ACTIVE_MODEL          LLM to use (default: gemini-2.0-flash)
  GEMINI_API_KEY        Google AI API key
  NETSUITE_SAVED_SEARCH_ID  Your saved search ID
  SLACK_BOT_TOKEN       Slack bot token
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
