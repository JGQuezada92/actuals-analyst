import { Server as SocketIOServer, Socket } from 'socket.io';
import { AgentBridge, AgentResponse } from './agent-bridge.js';
import { TraceStore } from './trace-store.js';
import { v4 as uuidv4 } from 'uuid';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: any;
}

export function setupSocketHandlers(
  io: SocketIOServer,
  agentBridge: AgentBridge,
  traceStore: TraceStore
) {
  io.on('connection', (socket: Socket) => {
    console.log(`✅ Client connected: ${socket.id}`);

    socket.on('chat:message', async (data: { message: string; options?: any }) => {
      const messageId = uuidv4();
      
      console.log(`[Socket] Received chat message: "${data.message.substring(0, 50)}..." (ID: ${messageId})`);
      
      try {
        socket.emit('chat:message:received', { id: messageId });
        socket.emit('chat:typing', { isTyping: true });

        const onProgress = (response: AgentResponse) => {
          console.log(`[Socket] Progress update: ${response.data?.message || 'Unknown phase'}`);
          socket.emit('chat:progress', { messageId, ...response });
        };

        console.log(`[Socket] Calling agentBridge.analyzeQuery...`);
        const result = await agentBridge.analyzeQuery(
          data.message,
          data.options || {},
          onProgress
        );

        console.log(`[Socket] Agent completed successfully`);
        socket.emit('chat:typing', { isTyping: false });

        const response: ChatMessage = {
          id: messageId,
          role: 'assistant',
          content: result.analysis || JSON.stringify(result, null, 2),
          timestamp: new Date().toISOString(),
          metadata: {
            calculations: result.calculations,
            charts: result.charts,
            traceId: result.trace_id,
            evaluation: result.evaluation_summary,
          },
        };

        socket.emit('chat:message:response', response);

      } catch (error: any) {
        console.error(`[Socket] Error processing chat message:`, error);
        console.error(`[Socket] Error stack:`, error.stack);
        console.error(`[Socket] Error message:`, error.message);
        
        socket.emit('chat:typing', { isTyping: false });
        socket.emit('chat:error', {
          messageId,
          error: error.message || 'An unknown error occurred',
          timestamp: new Date().toISOString(),
        });
      }
    });

    socket.on('traces:subscribe', () => {
      const onTraceAdded = (traceId: string) => {
        socket.emit('traces:new', { traceId });
      };

      traceStore.on('trace:added', onTraceAdded);

      socket.on('disconnect', () => {
        traceStore.off('trace:added', onTraceAdded);
      });
    });

    socket.on('disconnect', () => {
      console.log(`❌ Client disconnected: ${socket.id}`);
    });
  });
}

