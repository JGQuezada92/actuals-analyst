"""
Slack Bot Integration

Provides a Slack interface for the Financial Analyst Agent.
Uses Socket Mode for local development (no public URL needed).

Setup Requirements:
1. Create a Slack App at https://api.slack.com/apps
2. Enable Socket Mode
3. Add Bot Token Scopes
4. Install to workspace
5. Set environment variables
"""
import os
import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
import re

logger = logging.getLogger(__name__)

# Lazy imports for optional dependencies
def get_slack_dependencies():
    """Import Slack SDK dependencies."""
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        return App, SocketModeHandler, WebClient, SlackApiError
    except ImportError:
        raise ImportError(
            "Install Slack dependencies: pip install slack-bolt slack-sdk"
        )

from src.agents.financial_analyst import FinancialAnalystAgent, AgentResponse, get_financial_analyst
from config.settings import SlackConfig, get_config

class SlackBot:
    """
    Slack bot interface for the Financial Analyst Agent.
    
    Handles:
    - Slash commands (/analyze)
    - App mentions (@bot analyze...)
    - Direct messages
    - File uploads (charts)
    """
    
    def __init__(
        self,
        config: Optional[SlackConfig] = None,
        agent: Optional[FinancialAnalystAgent] = None,
    ):
        self.config = config or get_config().slack
        self.agent = agent or get_financial_analyst()
        
        # Import Slack dependencies
        App, _, WebClient, self.SlackApiError = get_slack_dependencies()
        
        # Initialize Slack app
        self.app = App(
            token=self.config.bot_token,
            signing_secret=self.config.signing_secret,
        )
        
        self.client = WebClient(token=self.config.bot_token)
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all Slack event handlers."""
        
        # Slash command: /analyze
        @self.app.command("/analyze")
        def handle_analyze_command(ack, command, respond):
            ack()  # Acknowledge immediately
            
            query = command.get("text", "").strip()
            user_id = command.get("user_id")
            channel_id = command.get("channel_id")
            
            if not query:
                respond(
                    "Please provide an analysis query. "
                    "Example: `/analyze What are our top revenue categories this month?`"
                )
                return
            
            # Send initial response
            respond(f"🔍 Analyzing: _{query}_\n\nThis may take a moment...")
            
            # Run analysis in background
            asyncio.run(self._run_analysis(query, channel_id, user_id))
        
        # App mention: @bot analyze...
        @self.app.event("app_mention")
        def handle_mention(event, say):
            text = event.get("text", "")
            user_id = event.get("user")
            channel_id = event.get("channel")
            
            # Remove bot mention from text
            query = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
            
            if not query:
                say(
                    "Hi! I'm your Financial Analyst. Ask me to analyze your NetSuite data. "
                    "For example: `@bot What are our expenses by department?`"
                )
                return
            
            say(f"🔍 Analyzing: _{query}_\n\nThis may take a moment...")
            
            asyncio.run(self._run_analysis(query, channel_id, user_id))
        
        # Direct message
        @self.app.event("message")
        def handle_direct_message(event, say, client):
            # Only handle DMs (no subtype means it's a regular message)
            if event.get("channel_type") != "im" or event.get("subtype"):
                return
            
            query = event.get("text", "").strip()
            user_id = event.get("user")
            channel_id = event.get("channel")
            
            if not query:
                return
            
            # Check for help command
            if query.lower() in ["help", "hi", "hello"]:
                say(self._get_help_message())
                return
            
            say(f"🔍 Analyzing: _{query}_\n\nThis may take a moment...")
            
            asyncio.run(self._run_analysis(query, channel_id, user_id))
    
    async def _run_analysis(self, query: str, channel_id: str, user_id: str):
        """Run the analysis and post results to Slack."""
        try:
            # Run the agent
            response = await self.agent.analyze(
                query=query,
                include_charts=True,
                max_iterations=3,
            )
            
            # Post the analysis
            self._post_analysis(response, channel_id, user_id)
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            self._post_error(str(e), channel_id, user_id)
    
    def _post_analysis(self, response: AgentResponse, channel_id: str, user_id: str):
        """Post analysis results to Slack."""
        
        # Format the main analysis message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Financial Analysis",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": response.analysis[:3000]  # Slack block limit
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*Data Rows:* {response.metadata['data_rows']} | "
                            f"*Model:* {response.metadata['model_used']} | "
                            f"*Quality Score:* {response.evaluation_summary.get('qualitative_score', 'N/A')}/10"
                        )
                    }
                ]
            }
        ]
        
        # Post main message
        try:
            result = self.client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text=f"Financial Analysis for <@{user_id}>",
            )
            thread_ts = result["ts"]
            
            # Upload charts in thread
            for chart in response.charts:
                try:
                    self.client.files_upload_v2(
                        channel=channel_id,
                        file=chart.file_path,
                        title=chart.title,
                        initial_comment=f"📈 {chart.title}",
                        thread_ts=thread_ts,
                    )
                except self.SlackApiError as e:
                    logger.error(f"Failed to upload chart: {e}")
            
            # Post key metrics in thread
            if response.calculations:
                metrics_text = "*Key Calculations:*\n" + "\n".join([
                    f"• {calc['metric_name']}: {calc['formatted_value']}"
                    for calc in response.calculations[:10]
                ])
                
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=metrics_text,
                    thread_ts=thread_ts,
                )
            
        except self.SlackApiError as e:
            logger.error(f"Failed to post to Slack: {e}")
            raise
    
    def _post_error(self, error_message: str, channel_id: str, user_id: str):
        """Post an error message to Slack."""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❌ *Analysis Failed*\n\n{error_message}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Please try again or contact support if the issue persists."
                    }
                ]
            }
        ]
        
        try:
            self.client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text=f"Analysis failed for <@{user_id}>",
            )
        except self.SlackApiError as e:
            logger.error(f"Failed to post error to Slack: {e}")
    
    def _get_help_message(self) -> str:
        """Get the help message."""
        return """
👋 *Hi! I'm your Financial Analyst Bot.*

I analyze your NetSuite saved search data and provide insights with charts.

*How to use me:*
• `/analyze [your question]` - Run an analysis
• `@bot [your question]` - Mention me in a channel
• DM me directly with your question

*Example questions:*
• "What are our top expense categories this month?"
• "Show me revenue trends over the past quarter"
• "Compare actual vs budget by department"
• "What's our cash flow breakdown?"

*Tips:*
• Be specific about time periods when relevant
• I work with your configured NetSuite saved search
• Charts are downloadable for sharing
"""
    
    def start(self):
        """Start the Slack bot in Socket Mode."""
        _, SocketModeHandler, _, _ = get_slack_dependencies()
        
        handler = SocketModeHandler(
            app=self.app,
            app_token=self.config.app_token,
        )
        
        logger.info("Starting Slack bot in Socket Mode...")
        handler.start()

def create_slack_bot() -> SlackBot:
    """Factory function to create a Slack bot."""
    return SlackBot()

# ============================================================
# SLACK APP SETUP INSTRUCTIONS
# ============================================================
"""
## Step-by-Step Slack App Setup

### 1. Create a Slack App
1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name: "Financial Analyst" (or your preference)
4. Select your workspace
5. Click "Create App"

### 2. Enable Socket Mode (Required for local development)
1. In your app settings, go to "Socket Mode" (left sidebar)
2. Toggle "Enable Socket Mode" ON
3. Give your token a name (e.g., "local-dev")
4. Copy the generated App-Level Token (starts with xapp-)
5. Save this as SLACK_APP_TOKEN

### 3. Configure Bot Token Scopes
1. Go to "OAuth & Permissions" (left sidebar)
2. Under "Scopes" → "Bot Token Scopes", add:
   - app_mentions:read
   - channels:history
   - channels:read
   - chat:write
   - commands
   - files:write
   - groups:history
   - groups:read
   - im:history
   - im:read
   - im:write
   - users:read

### 4. Enable Events
1. Go to "Event Subscriptions" (left sidebar)
2. Toggle "Enable Events" ON
3. Under "Subscribe to bot events", add:
   - app_mention
   - message.channels
   - message.groups
   - message.im

### 5. Create Slash Command
1. Go to "Slash Commands" (left sidebar)
2. Click "Create New Command"
3. Command: /analyze
4. Short Description: "Analyze NetSuite financial data"
5. Usage Hint: "[your analysis question]"
6. Click "Save"

### 6. Install App to Workspace
1. Go to "Install App" (left sidebar)
2. Click "Install to Workspace"
3. Authorize the permissions
4. Copy the Bot User OAuth Token (starts with xoxb-)
5. Save this as SLACK_BOT_TOKEN

### 7. Get Signing Secret
1. Go to "Basic Information" (left sidebar)
2. Under "App Credentials", find "Signing Secret"
3. Copy it and save as SLACK_SIGNING_SECRET

### 8. Set Environment Variables
Create a .env file with:

```
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_APP_TOKEN=xapp-your-app-token
```

### 9. Invite Bot to Channels
In Slack, invite the bot to any channel where you want to use it:
/invite @Financial Analyst

### 10. Test the Bot
- Try: /analyze What are our top expenses?
- Or mention: @Financial Analyst show revenue trends
- Or DM the bot directly

## Deployment Options

### Local Development (Socket Mode)
- Works behind firewalls
- No public URL needed
- Just run: python -m src.integrations.slack_bot

### Cloud Deployment (HTTP Mode)
For production, you may want to switch to HTTP mode:
1. Deploy to a server with a public URL
2. Disable Socket Mode in Slack settings
3. Set Request URL to: https://your-server.com/slack/events
4. Use Flask/FastAPI adapter instead of SocketModeHandler

Recommended cloud options:
- AWS Lambda + API Gateway
- Google Cloud Run
- Heroku
- Railway
- Render
"""
