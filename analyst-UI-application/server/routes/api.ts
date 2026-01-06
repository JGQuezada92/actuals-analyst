import { Router } from 'express';
import { AgentBridge } from '../services/agent-bridge.js';

export function setupApiRoutes(agentBridge: AgentBridge): Router {
  const router = Router();

  router.post('/analyze', async (req, res) => {
    try {
      const { query, options } = req.body;
      const result = await agentBridge.analyzeQuery(query, options);
      res.json(result);
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  router.get('/setup', async (req, res) => {
    try {
      const config = await agentBridge.getConfiguration();
      res.json(config);
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  router.get('/registry/stats', async (req, res) => {
    try {
      const stats = await agentBridge.getRegistryStats();
      res.json(stats);
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  router.post('/registry/refresh', async (req, res) => {
    try {
      await agentBridge.refreshRegistry();
      res.json({ success: true });
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  return router;
}

