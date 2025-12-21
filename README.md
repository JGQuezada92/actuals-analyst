# NetSuite Financial Analyst Agent

An **Accuracy-First Agentic AI System** that retrieves and analyzes financial data from NetSuite saved searches, delivering professional insights via Slack.

Built on the [Accuracy-First Agentic AI Framework](docs/FRAMEWORK.md), this agent prioritizes correctness over speed, with rigorous evaluation at every step.

## Key Features

- 🔄 **Model-Agnostic**: Swap between Gemini, Claude, or GPT with a single environment variable
- 🎯 **Accuracy-First**: Deterministic calculations + LLM interpretation = reliable results
- 🔍 **Self-Evaluation**: Reflection pattern with cross-model quality assessment
- 📊 **Professional Charts**: Auto-generated visualizations for Slack
- 💬 **Slack Integration**: Natural language queries from any channel

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         SLACK BOT                            │
│  /analyze "query"  │  @bot query  │  Direct Message         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   FINANCIAL ANALYST AGENT                    │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Phase 1  │→ │ Phase 2  │→ │ Phase 3  │→ │ Phase 4  │    │
│  │  Data    │  │  Calc    │  │  Charts  │  │ Analysis │    │
│  │Retrieval │  │(Determ.) │  │   Gen    │  │+Reflect  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                                                     │        │
│                                                     ▼        │
│                                            ┌──────────────┐  │
│                                            │   Phase 5    │  │
│                                            │  Evaluation  │  │
│                                            │ (Cross-Model)│  │
│                                            └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       MODEL ROUTER                           │
│                                                              │
│   ACTIVE_MODEL env var → Routes to correct provider          │
│                                                              │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│   │ Gemini  │     │ Claude  │     │  GPT    │              │
│   └─────────┘     └─────────┘     └─────────┘              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Clone and Install

```bash
git clone <repository>
cd netsuite-analyst
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Validate Setup

```bash
python main.py setup
```

### 4. Start the Bot

```bash
python main.py slack
```

## Configuration

### Model Selection

Change LLM providers by setting `ACTIVE_MODEL`:

```bash
# Use Gemini (default, lowest cost)
ACTIVE_MODEL=gemini-2.0-flash

# Use Claude (highest accuracy)
ACTIVE_MODEL=claude-sonnet-4

# Use GPT-4
ACTIVE_MODEL=gpt-4o
```

Only the API key for your active model is required.

### NetSuite Setup

1. **Create a Token-Based Authentication (TBA) integration**:
   - Go to: Setup > Integration > Manage Integrations
   - Create new integration with TBA enabled
   - Note the Consumer Key and Secret

2. **Create Access Tokens**:
   - Go to: Setup > Users/Roles > Access Tokens
   - Create token for your integration
   - Note the Token ID and Secret

3. **Get Your Saved Search ID**:
   - Open your saved search in NetSuite
   - The ID is in the URL: `...&id=customsearch_XXX`

### Slack Setup

See detailed instructions in [src/integrations/slack_bot.py](src/integrations/slack_bot.py).

Quick summary:
1. Create Slack App at https://api.slack.com/apps
2. Enable Socket Mode
3. Add required Bot Token Scopes
4. Create `/analyze` slash command
5. Install to workspace
6. Copy tokens to `.env`

## Usage

### Via Slack

```
/analyze What are our top expense categories this month?
```

```
@FinancialAnalyst Show me revenue trends by department
```

### Via Command Line

```bash
# Run analysis
python main.py analyze "What's our cash flow breakdown?"

# With options
python main.py analyze "Revenue analysis" --no-charts --iterations 5
```

## Framework Principles

This agent implements the **Accuracy-First Agentic AI Framework**:

### 1. Deterministic + Probabilistic Separation
- **Calculations**: Performed by code (always consistent)
- **Interpretation**: Performed by LLM (with evaluation)

### 2. Evaluation-First Development
- Cross-model evaluation (generate with Gemini, judge with Claude)
- Quantified accuracy metrics before any output
- Reflection pattern for iterative improvement

### 3. Model-Agnostic Architecture
- Single `ACTIVE_MODEL` variable controls all LLM routing
- Swap models without code changes
- Provider-specific optimization via prompt templates

### 4. Phased Quality Gates
| Phase | Description | Output |
|-------|-------------|--------|
| 1 | Data Retrieval | Validated NetSuite data |
| 2 | Calculations | Deterministic metrics |
| 3 | Chart Generation | PNG visualizations |
| 4 | Analysis + Reflection | Refined narrative |
| 5 | Evaluation | Quality scores |

## Project Structure

```
netsuite-analyst/
├── main.py                     # Entry point & CLI
├── config/
│   └── settings.py             # Model-agnostic configuration
├── src/
│   ├── core/
│   │   └── model_router.py     # LLM abstraction layer
│   ├── agents/
│   │   └── financial_analyst.py # Main agent logic
│   ├── tools/
│   │   ├── netsuite_client.py  # NetSuite data retrieval
│   │   ├── calculator.py       # Deterministic calculations
│   │   └── charts.py           # Visualization generation
│   ├── evaluation/
│   │   └── evaluator.py        # LLM-as-a-Judge system
│   └── integrations/
│       └── slack_bot.py        # Slack interface
├── tests/
├── docs/
├── requirements.txt
├── .env.example
└── README.md
```

## Extending the Agent

### Adding New Calculations

Edit `src/tools/calculator.py`:

```python
def my_new_ratio(self, numerator: float, denominator: float) -> CalculationResult:
    value = self._safe_divide(numerator, denominator)
    return CalculationResult(
        metric_name="My New Ratio",
        value=value,
        formatted_value=self._format_ratio(value),
        metric_type=MetricType.PROFITABILITY,
        inputs={"numerator": numerator, "denominator": denominator},
        formula="Numerator / Denominator",
        interpretation_guide="Explanation for LLM...",
    )
```

### Adding New Models

Edit `config/settings.py`:

```python
MODEL_REGISTRY["new-model"] = ModelConfig(
    provider=ModelProvider.OPENAI,  # or new provider
    model_name="new-model-name",
    api_key_env="NEW_MODEL_API_KEY",
)
```

### Custom Evaluation Criteria

Edit `src/evaluation/evaluator.py` to add domain-specific quality dimensions.

## Deployment

### Local Development (Socket Mode)
Works behind firewalls, no public URL needed.

```bash
python main.py slack
```

### Cloud Deployment
For production, consider:
- **AWS Lambda** + API Gateway
- **Google Cloud Run**
- **Railway** or **Render**

Switch from Socket Mode to HTTP mode by updating the Slack handler.

## Troubleshooting

### "Missing API key" error
```bash
python main.py setup  # Shows which keys are missing
```

### NetSuite authentication fails
- Verify TBA tokens are active
- Check role has saved search access
- Confirm account ID format

### Slack bot not responding
- Verify Socket Mode is enabled
- Check app token (xapp-) is correct
- Ensure bot is invited to channel

## License

MIT License - See LICENSE file for details.

## Acknowledgments

Built on the Accuracy-First Agentic AI Framework, developed through practical experience building production-grade financial analysis systems.
