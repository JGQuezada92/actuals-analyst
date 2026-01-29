import { Server as SocketIOServer, Socket } from 'socket.io';
import { AgentBridge, AgentResponse } from './agent-bridge.js';
import { TraceStore } from './trace-store.js';
import { v4 as uuidv4 } from 'uuid';

interface ClarificationOption {
  id: number;
  label: string;
  description: string;
  value: string;
}

interface ClarificationData {
  requiresClarification: boolean;
  clarificationMessage: string;
  ambiguousTerms: string[];
  options: ClarificationOption[];
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: any;
}

/**
 * Parse clarification message from the agent and extract structured options.
 * Handles messages like:
 * "The term \"r&d\" could mean:\n\n  1. R&D Accounts (52xxx account numbers)\n     (Filter by R&D expense accounts...)\n\n  2. R&D Departments..."
 */
function parseClarificationOptions(
  clarificationMessage: string,
  ambiguousTerms: string[]
): ClarificationData {
  const options: ClarificationOption[] = [];
  
  // Split by numbered items (1., 2., 3., etc.)
  const lines = clarificationMessage.split('\n');
  let currentOption: Partial<ClarificationOption> | null = null;
  let description: string[] = [];
  
  for (const line of lines) {
    const trimmedLine = line.trim();
    
    // Match numbered options like "1. R&D Accounts (52xxx account numbers)"
    const optionMatch = trimmedLine.match(/^(\d+)\.\s+(.+)/);
    
    if (optionMatch) {
      // Save previous option if exists
      if (currentOption && currentOption.label) {
        options.push({
          id: currentOption.id!,
          label: currentOption.label,
          description: description.join(' ').trim(),
          value: `Option ${currentOption.id}: ${currentOption.label}`,
        });
        description = [];
      }
      
      currentOption = {
        id: parseInt(optionMatch[1]),
        label: optionMatch[2].trim(),
      };
    } else if (currentOption && trimmedLine.startsWith('(') && trimmedLine.endsWith(')')) {
      // This is a description line in parentheses
      description.push(trimmedLine.slice(1, -1));
    } else if (currentOption && trimmedLine && !trimmedLine.toLowerCase().includes('please specify')) {
      // Additional description text
      description.push(trimmedLine);
    }
  }
  
  // Don't forget the last option
  if (currentOption && currentOption.label) {
    options.push({
      id: currentOption.id!,
      label: currentOption.label,
      description: description.join(' ').trim(),
      value: `Option ${currentOption.id}: ${currentOption.label}`,
    });
  }
  
  // Extract the question/context from the beginning of the message
  const contextMatch = clarificationMessage.match(/^(.+?)(?:\n\s*\n|\n\s*1\.)/s);
  const questionContext = contextMatch ? contextMatch[1].trim() : 'Please clarify your question:';
  
  return {
    requiresClarification: true,
    clarificationMessage: questionContext,
    ambiguousTerms,
    options,
  };
}

export function setupSocketHandlers(
  io: SocketIOServer,
  agentBridge: AgentBridge,
  traceStore: TraceStore
) {
  io.on('connection', (socket: Socket) => {
    console.log(`✅ Client connected: ${socket.id}`);
    
    // Track session ID for this socket connection (conversation continuity)
    let sessionId: string | undefined;

    socket.on('chat:message', async (data: { message: string; options?: any; sessionId?: string }) => {
      const messageId = uuidv4();
      
      // Use client-provided sessionId if available (for reconnection continuity)
      // Otherwise fall back to server-side tracked sessionId
      const effectiveSessionId = data.sessionId || sessionId;
      
      console.log(`[Socket] Received chat message: "${data.message.substring(0, 50)}..." (ID: ${messageId}, Session: ${effectiveSessionId || 'new'})`);
      
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
          { ...data.options, sessionId: effectiveSessionId },  // Pass sessionId to Python agent
          onProgress
        );

        console.log(`[Socket] Agent completed successfully`);
        socket.emit('chat:typing', { isTyping: false });
        
        // Extract session_id from Python response for next message
        // This ensures conversation continuity across messages
        if (result.metadata?.session_id) {
          const newSessionId = result.metadata.session_id;
          if (newSessionId !== sessionId) {
            console.log(`[Socket] Session ID updated: ${sessionId || 'none'} -> ${newSessionId}`);
            sessionId = newSessionId;
          }
        }

        // Parse clarification options from the message if requires_clarification
        let clarificationData = undefined;
        if (result.requires_clarification && result.clarification_message) {
          clarificationData = parseClarificationOptions(
            result.clarification_message,
            result.ambiguous_terms || []
          );
        }

        const response: ChatMessage = {
          id: messageId,
          role: 'assistant',
          content: result.requires_clarification 
            ? '' // Empty content for clarification messages - UI will render the clarification component
            : (result.analysis || JSON.stringify(result, null, 2)),
          timestamp: new Date().toISOString(),
          metadata: {
            calculations: result.calculations,
            charts: result.charts,
            traceId: result.trace_id,
            evaluation: result.evaluation_summary,
            sessionId: sessionId,  // Include session ID in response metadata
            clarification: clarificationData,
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

