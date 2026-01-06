# Installation Guide

## Step 1: Install Server Dependencies

```bash
cd analyst-UI-application
npm install
```

## Step 2: Setup React Client

### Option A: Automated Setup (Recommended)

**Windows:**
```powershell
.\setup-client.ps1
```

**Mac/Linux:**
```bash
chmod +x setup-client.sh
./setup-client.sh
```

### Option B: Manual Setup

```bash
cd client

# Create Vite React TypeScript app
npm create vite@latest . -- --template react-ts

# Install all dependencies
npm install

# Install UI libraries
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu \
  @radix-ui/react-scroll-area @radix-ui/react-separator \
  @radix-ui/react-slot @radix-ui/react-tabs @radix-ui/react-tooltip \
  @radix-ui/react-avatar @radix-ui/react-collapsible

# Install styling
npm install class-variance-authority clsx tailwind-merge tailwindcss-animate
npm install lucide-react recharts date-fns

# Install state & data
npm install zustand socket.io-client react-router-dom @tanstack/react-query

# Install notifications
npm install sonner

# Install dev dependencies
npm install -D tailwindcss postcss autoprefixer

# Initialize Tailwind
npx tailwindcss init -p

# Initialize shadcn/ui
npx shadcn@latest init
# When prompted:
# - Style: Default
# - Base color: Neutral
# - CSS variables: Yes

# Add core components
npx shadcn@latest add button card input textarea badge tabs \
  dialog dropdown-menu scroll-area separator tooltip avatar \
  sheet skeleton table

cd ..
```

## Step 3: Configure Environment

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

**Note:** On Windows, you may need `PYTHON_PATH=py -3.13` or the full path to your Python executable.

## Step 4: Start Development Servers

```bash
# From analyst-UI-application directory
npm run dev
```

This starts:
- Server on http://localhost:3001
- Client on http://localhost:5173

## Troubleshooting

### Python Path Issues

If the agent doesn't run, check your Python path:

```bash
# Test Python command
python --version
# or
py -3.13 --version

# Update .env with correct path
PYTHON_PATH=py -3.13
```

### Port Already in Use

Change ports in `.env`:
```env
PORT=3002
CORS_ORIGIN=http://localhost:5174
```

### Client Build Errors

Make sure all dependencies are installed:
```bash
cd client
rm -rf node_modules package-lock.json
npm install
```

## Next Steps

After installation, the frontend components need to be created. See the implementation guide for:
- React component files
- Zustand stores
- Socket.IO hooks
- Routing configuration

