# Quick Start Guide

## Prerequisites

- Node.js 18+ installed
- Python 3.11+ installed (for the agent)
- The parent `actuals-analyst` project configured

## Installation Steps

### 1. Install Server Dependencies

```bash
cd analyst-UI-application
npm install
```

### 2. Setup React Client

**Windows:**
```powershell
.\setup-client.ps1
```

**Mac/Linux:**
```bash
chmod +x setup-client.sh
./setup-client.sh
```

**Or manually:**
```bash
cd client
npm create vite@latest . -- --template react-ts
npm install

# Install UI dependencies
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu \
  @radix-ui/react-scroll-area @radix-ui/react-separator \
  @radix-ui/react-slot @radix-ui/react-tabs @radix-ui/react-tooltip \
  @radix-ui/react-avatar @radix-ui/react-collapsible

npm install class-variance-authority clsx tailwind-merge tailwindcss-animate
npm install lucide-react recharts date-fns
npm install zustand socket.io-client react-router-dom @tanstack/react-query
npm install sonner

npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Initialize shadcn/ui
npx shadcn@latest init
# Choose: Default style, Neutral color, CSS variables: Yes

# Add components
npx shadcn@latest add button card input textarea badge tabs \
  dialog dropdown-menu scroll-area separator tooltip avatar \
  sheet skeleton table

cd ..
```

### 3. Configure Environment

Create `analyst-UI-application/.env`:

```env
PORT=3001
NODE_ENV=development
PYTHON_PATH=python
AGENT_SCRIPT_PATH=../main.py
TRACES_DIR=../traces
CONFIG_DIR=../config
CORS_ORIGIN=http://localhost:5173
```

**Note:** On Windows, you may need:
```env
PYTHON_PATH=py -3.13
```

### 4. Start Development Servers

```bash
# From analyst-UI-application directory
npm run dev
```

This starts:
- **Server**: http://localhost:3001
- **Client**: http://localhost:5173

## Usage

1. Open http://localhost:5173 in your browser
2. Navigate to **Chat** tab
3. Ask a question like: "What are our total expenses YTD?"
4. Watch real-time progress updates
5. View results with calculations and charts

## Features

- 💬 **Chat Interface** - Clean, intuitive chat UI
- 📊 **Admin Dashboard** - Metrics and monitoring
- 🔍 **Trace Viewer** - Debug queries with span-level detail
- ⚡ **Real-time Updates** - WebSocket-powered responses
- 🎨 **Dark Mode** - Toggle theme in header

## Troubleshooting

### Python Not Found
Update `.env` with correct Python path:
```env
PYTHON_PATH=C:\Python313\python.exe
# or
PYTHON_PATH=py -3.13
```

### Port Already in Use
Change ports in `.env`:
```env
PORT=3002
CORS_ORIGIN=http://localhost:5174
```

### Client Build Errors
```bash
cd client
rm -rf node_modules package-lock.json
npm install
```

### WebSocket Connection Failed
- Check server is running on port 3001
- Verify CORS_ORIGIN matches client URL
- Check browser console for errors

## Project Structure

```
analyst-UI-application/
├── server/              # Node.js backend
│   ├── index.ts         # Express + Socket.IO
│   ├── routes/          # API routes
│   └── services/        # Business logic
├── client/              # React frontend
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── pages/      # Page components
│   │   ├── stores/     # Zustand stores
│   │   └── hooks/      # Custom hooks
│   └── package.json
└── package.json         # Root package.json
```

## Next Steps

- Customize the UI theme
- Add more admin features
- Enhance trace viewer
- Add chart visualization
- Implement prompt management UI

