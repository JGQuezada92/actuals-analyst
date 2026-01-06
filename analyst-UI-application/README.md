# Financial Analyst UI Application

Beautiful chat interface and admin dashboard for the NetSuite Financial Analyst Agent.

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.11+ (for the agent)
- The parent `actuals-analyst` project configured

### Installation

```bash
# Install server dependencies
npm install

# Install client dependencies
cd client
npm install
cd ..
```

### Development

```bash
# Start both server and client
npm run dev

# Or start separately
npm run dev:server  # Server on http://localhost:3001
npm run dev:client  # Client on http://localhost:5173
```

### Configuration

Edit `.env` to configure paths:

```env
PYTHON_PATH=python              # or py -3.13 on Windows
AGENT_SCRIPT_PATH=../main.py
TRACES_DIR=../traces
CONFIG_DIR=../config
```

## Project Structure

```
analyst-UI-application/
├── server/              # Node.js backend
│   ├── index.ts         # Express + Socket.IO server
│   ├── routes/          # API routes
│   └── services/        # Business logic
├── client/              # React frontend (Vite)
│   └── src/             # React source code
└── package.json         # Root package.json
```

## Features

- 💬 **Chat Interface** - Clean, intuitive chat UI for end users
- 📊 **Admin Dashboard** - Comprehensive metrics and monitoring
- 🔍 **Trace Viewer** - Debug queries with span-level detail
- ⚡ **Real-time Updates** - WebSocket-powered instant responses
- 🎨 **Modern UI** - Built with shadcn/ui and Tailwind CSS

## API Endpoints

- `GET /health` - Health check
- `POST /api/analyze` - Analyze a query
- `GET /api/traces` - List traces
- `GET /api/traces/stats` - Trace statistics
- `GET /api/traces/:id` - Get trace details
- `GET /api/config/prompts` - List prompts

## WebSocket Events

**Client → Server:**
- `chat:message` - Send a query
- `traces:subscribe` - Subscribe to trace updates

**Server → Client:**
- `chat:message:received` - Message received confirmation
- `chat:typing` - Typing indicator
- `chat:progress` - Progress updates
- `chat:message:response` - Final response
- `chat:error` - Error occurred
- `traces:new` - New trace available

## License

MIT

