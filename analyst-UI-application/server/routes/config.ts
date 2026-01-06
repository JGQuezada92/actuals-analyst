import { Router } from 'express';
import { ConfigStore } from '../services/config-store.js';

export function setupConfigRoutes(configStore: ConfigStore): Router {
  const router = Router();

  router.get('/prompts', async (req, res) => {
    try {
      const prompts = await configStore.listPrompts();
      res.json(prompts);
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  router.get('/prompts/:name', async (req, res) => {
    try {
      const prompt = await configStore.getPrompt(req.params.name, req.query.version as string);
      res.json(prompt);
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  return router;
}

