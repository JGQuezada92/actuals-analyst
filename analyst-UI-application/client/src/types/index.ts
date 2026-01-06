export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: {
    calculations?: any[];
    charts?: any[];
    traceId?: string;
    evaluation?: any;
  };
}

export interface AgentResponse {
  id: string;
  type: 'progress' | 'analysis' | 'calculation' | 'chart' | 'error' | 'complete';
  data: any;
  timestamp: string;
}

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
  spans: Span[];
}

export interface Span {
  span_id: string;
  name: string;
  kind: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number;
  status: 'ok' | 'error' | 'timeout';
  parent_span_id: string | null;
  attributes: Record<string, any>;
  events: Array<{
    name: string;
    timestamp: string;
    attributes: Record<string, any>;
  }>;
  llm_usage?: {
    model: string;
    provider: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    latency_ms: number;
  };
  error_message?: string | null;
}

export interface TraceStats {
  totalTraces: number;
  successRate: number;
  totalCost: number;
  avgDuration: number;
  avgCost: number;
  avgTokens: number;
  tracesByStatus: Record<string, number>;
  tracesByDay: Array<{ date: string; count: number; cost: number }>;
}

