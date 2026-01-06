import fs from 'fs';
import path from 'path';
import { EventEmitter } from 'events';
import chokidar from 'chokidar';

export interface Trace {
  trace_id: string;
  query: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number;
  status: 'ok' | 'error' | 'timeout';
  error_message: string | null;
  user_id: string | null;
  session_id: string | null;
  channel: string | null;
  metrics: {
    total_input_tokens: number;
    total_output_tokens: number;
    total_tokens: number;
    total_llm_calls: number;
    estimated_cost_usd: number;
    evaluation_score: number | null;
    passed_evaluation: boolean | null;
  };
  spans: any[];
}

export interface TraceListOptions {
  limit?: number;
  offset?: number;
  status?: 'ok' | 'error' | 'timeout';
  search?: string;
}

export class TraceStore extends EventEmitter {
  private tracesDir: string;
  private watcher: chokidar.FSWatcher | null = null;
  private traceCache: Map<string, Trace> = new Map();

  constructor(tracesDir: string) {
    super();
    this.tracesDir = tracesDir;
    this.ensureDirectory();
    this.startWatching();
  }

  private ensureDirectory() {
    if (!fs.existsSync(this.tracesDir)) {
      fs.mkdirSync(this.tracesDir, { recursive: true });
    }
  }

  private startWatching() {
    this.watcher = chokidar.watch(path.join(this.tracesDir, '*.json'), {
      persistent: true,
      ignoreInitial: false,
    });

    this.watcher.on('add', (filePath) => {
      this.loadTrace(filePath);
      this.emit('trace:added', path.basename(filePath, '.json'));
    });

    this.watcher.on('change', (filePath) => {
      this.loadTrace(filePath);
      this.emit('trace:updated', path.basename(filePath, '.json'));
    });
  }

  private loadTrace(filePath: string) {
    try {
      const content = fs.readFileSync(filePath, 'utf-8');
      const trace = JSON.parse(content) as Trace;
      this.traceCache.set(trace.trace_id, trace);
    } catch (error) {
      console.error(`Failed to load trace: ${filePath}`, error);
    }
  }

  isHealthy(): boolean {
    return fs.existsSync(this.tracesDir);
  }

  async listTraces(options: TraceListOptions = {}): Promise<{
    traces: Trace[];
    total: number;
    hasMore: boolean;
  }> {
    const { limit = 20, offset = 0, status, search } = options;

    if (this.traceCache.size === 0) {
      await this.loadAllTraces();
    }

    let traces = Array.from(this.traceCache.values());

    if (status) {
      traces = traces.filter(t => t.status === status);
    }

    if (search) {
      const searchLower = search.toLowerCase();
      traces = traces.filter(t => 
        t.query.toLowerCase().includes(searchLower) ||
        t.trace_id.toLowerCase().includes(searchLower)
      );
    }

    traces.sort((a, b) => 
      new Date(b.start_time).getTime() - new Date(a.start_time).getTime()
    );

    const total = traces.length;
    const paginatedTraces = traces.slice(offset, offset + limit);

    return {
      traces: paginatedTraces,
      total,
      hasMore: offset + limit < total,
    };
  }

  private async loadAllTraces(): Promise<void> {
    const files = fs.readdirSync(this.tracesDir)
      .filter(f => f.endsWith('.json') && f.startsWith('trace_'));

    for (const file of files) {
      const filePath = path.join(this.tracesDir, file);
      this.loadTrace(filePath);
    }
  }

  async getTrace(traceId: string): Promise<Trace | null> {
    if (this.traceCache.has(traceId)) {
      return this.traceCache.get(traceId)!;
    }

    const filePath = path.join(this.tracesDir, `${traceId}.json`);
    if (fs.existsSync(filePath)) {
      this.loadTrace(filePath);
      return this.traceCache.get(traceId) || null;
    }

    return null;
  }

  async getStats(): Promise<{
    totalTraces: number;
    successRate: number;
    totalCost: number;
    avgDuration: number;
    avgCost: number;
    avgTokens: number;
    tracesByStatus: Record<string, number>;
    tracesByDay: Array<{ date: string; count: number; cost: number }>;
  }> {
    if (this.traceCache.size === 0) {
      await this.loadAllTraces();
    }

    const traces = Array.from(this.traceCache.values());
    const total = traces.length;

    if (total === 0) {
      return {
        totalTraces: 0,
        successRate: 0,
        totalCost: 0,
        avgDuration: 0,
        avgCost: 0,
        avgTokens: 0,
        tracesByStatus: {},
        tracesByDay: [],
      };
    }

    const successCount = traces.filter(t => t.status === 'ok').length;
    const totalCost = traces.reduce((sum, t) => sum + t.metrics.estimated_cost_usd, 0);
    const totalDuration = traces.reduce((sum, t) => sum + t.duration_ms, 0);
    const totalTokens = traces.reduce((sum, t) => sum + t.metrics.total_tokens, 0);

    const tracesByStatus: Record<string, number> = {};
    for (const trace of traces) {
      tracesByStatus[trace.status] = (tracesByStatus[trace.status] || 0) + 1;
    }

    const tracesByDay: Map<string, { count: number; cost: number }> = new Map();
    for (const trace of traces) {
      const date = trace.start_time.split('T')[0];
      const existing = tracesByDay.get(date) || { count: 0, cost: 0 };
      tracesByDay.set(date, {
        count: existing.count + 1,
        cost: existing.cost + trace.metrics.estimated_cost_usd,
      });
    }

    return {
      totalTraces: total,
      successRate: successCount / total,
      totalCost,
      avgDuration: totalDuration / total,
      avgCost: totalCost / total,
      avgTokens: totalTokens / total,
      tracesByStatus,
      tracesByDay: Array.from(tracesByDay.entries())
        .map(([date, data]) => ({ date, ...data }))
        .sort((a, b) => a.date.localeCompare(b.date)),
    };
  }

  close() {
    if (this.watcher) {
      this.watcher.close();
    }
  }
}

