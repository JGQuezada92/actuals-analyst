import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { formatDate, formatCurrency, formatDuration } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Trace } from '@/types';

export function TracesPage() {
  const [traces, setTraces] = useState<Trace[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetchTraces();
  }, [search]);

  const fetchTraces = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '20' });
      if (search) params.append('search', search);
      
      const res = await fetch(`/api/traces?${params}`);
      const data = await res.json();
      setTraces(data.traces || []);
    } catch (error) {
      console.error('Failed to fetch traces:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Traces</h1>
        <Input
          placeholder="Search traces..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64"
        />
      </div>

      {loading ? (
        <div className="text-center py-8 text-muted-foreground">Loading...</div>
      ) : traces.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No traces found</div>
      ) : (
        <div className="space-y-2">
          {traces.map((trace) => (
            <Card key={trace.trace_id} className="cursor-pointer hover:bg-accent/50">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{trace.query}</CardTitle>
                  <Badge variant={trace.status === 'ok' ? 'default' : 'destructive'}>
                    {trace.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-4 gap-4 text-sm">
                  <div>
                    <div className="text-muted-foreground">Duration</div>
                    <div className="font-medium">{formatDuration(trace.duration_ms)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Cost</div>
                    <div className="font-medium">{formatCurrency(trace.metrics.estimated_cost_usd)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Tokens</div>
                    <div className="font-medium">{trace.metrics.total_tokens.toLocaleString()}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Time</div>
                    <div className="font-medium">{formatDate(trace.start_time)}</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

