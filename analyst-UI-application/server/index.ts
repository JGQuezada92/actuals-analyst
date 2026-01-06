import express from 'express';
import { createServer } from 'http';
import { Server as SocketIOServer } from 'socket.io';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

import { setupApiRoutes } from './routes/api.js';
import { setupTraceRoutes } from './routes/traces.js';
import { setupConfigRoutes } from './routes/config.js';
import { setupSocketHandlers } from './services/socket-handler.js';
import { AgentBridge } from './services/agent-bridge.js';
import { TraceStore } from './services/trace-store.js';
import { ConfigStore } from './services/config-store.js';

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const httpServer = createServer(app);

// CORS configuration
const corsOrigin = process.env.CORS_ORIGIN || 'http://localhost:5173';
app.use(cors({ origin: corsOrigin, credentials: true }));
app.use(express.json());

// Socket.IO setup
const io = new SocketIOServer(httpServer, {
  cors: {
    origin: corsOrigin,
    methods: ['GET', 'POST'],
    credentials: true,
  },
});

// Initialize services
const tracesDir = path.resolve(__dirname, '..', process.env.TRACES_DIR || '../traces');
const configDir = path.resolve(__dirname, '..', process.env.CONFIG_DIR || '../config');
const agentScriptPath = path.resolve(__dirname, '..', process.env.AGENT_SCRIPT_PATH || '../main.py');
const pythonPath = process.env.PYTHON_PATH || 'python';

console.log('📁 Traces directory:', tracesDir);
console.log('📁 Config directory:', configDir);
console.log('🐍 Agent script:', agentScriptPath);

const traceStore = new TraceStore(tracesDir);
const configStore = new ConfigStore(configDir);
const agentBridge = new AgentBridge(agentScriptPath, pythonPath);

// Setup routes
app.use('/api', setupApiRoutes(agentBridge));
app.use('/api/traces', setupTraceRoutes(traceStore));
app.use('/api/config', setupConfigRoutes(configStore));

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    services: {
      traceStore: traceStore.isHealthy(),
      agentBridge: agentBridge.isHealthy(),
    }
  });
});

// Setup WebSocket handlers
setupSocketHandlers(io, agentBridge, traceStore);

// Serve static files in production
if (process.env.NODE_ENV === 'production') {
  app.use(express.static(path.join(__dirname, '../client/dist')));
  app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, '../client/dist/index.html'));
  });
}

// Start server
const PORT = parseInt(process.env.PORT || '3001', 10);
httpServer.listen(PORT, () => {
  console.log(`🚀 Server running on http://localhost:${PORT}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully...');
  agentBridge.shutdown();
  traceStore.close();
  httpServer.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});

