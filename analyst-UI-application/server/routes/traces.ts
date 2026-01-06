import { Router } from 'express';
import { TraceStore } from '../services/trace-store.js';

export function setupTraceRoutes(traceStore: TraceStore): Router {
  const router = Router();

  router.get('/', async (req, res) => {
    try {
      const options = {
        limit: parseInt(req.query.limit as string) || 20,
        offset: parseInt(req.query.offset as string) || 0,
        status: req.query.status as any,
        search: req.query.search as string,
      };
      const result = await traceStore.listTraces(options);
      res.json(result);
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  router.get('/stats', async (req, res) => {
    try {
      const stats = await traceStore.getStats();
      res.json(stats);
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  router.get('/:id', async (req, res) => {
    try {
      const trace = await traceStore.getTrace(req.params.id);
      if (!trace) {
        return res.status(404).json({ error: 'Trace not found' });
      }
      res.json(trace);
    } catch (error: any) {
      res.status(500).json({ error: error.message });
    }
  });

  return router;
}

