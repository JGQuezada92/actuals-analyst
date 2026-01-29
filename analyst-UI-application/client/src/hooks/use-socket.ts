import { useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { useChatStore } from '@/stores/chat-store';
import { ChatMessage, AgentResponse } from '@/types';

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:3001';

export function useSocket() {
  const socketRef = useRef<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const { addMessage, setLoading, setPhase, setSessionId, sessionId } = useChatStore();

  useEffect(() => {
    // Initialize socket
    // Allow Socket.IO to negotiate transport (polling first, then upgrade to websocket)
    socketRef.current = io(SOCKET_URL, {
      transports: ['polling', 'websocket'],
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
    });

    const socket = socketRef.current;

    socket.on('connect', () => {
      console.log('✅ Connected to server');
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('❌ Disconnected from server');
      setIsConnected(false);
    });

    socket.on('chat:message:received', (data: { id: string }) => {
      console.log('Message received:', data.id);
    });

    socket.on('chat:typing', (data: { isTyping: boolean }) => {
      setLoading(data.isTyping);
    });

    socket.on('chat:progress', (data: { messageId: string } & AgentResponse) => {
      if (data.type === 'progress' && data.data?.message) {
        setPhase(data.data.message);
      }
    });

    socket.on('chat:message:response', (response: ChatMessage) => {
      addMessage(response);
      setLoading(false);
      setPhase(null);
      
      // Extract and store sessionId from response for conversation continuity
      if (response.metadata?.sessionId) {
        console.log(`📎 Session ID received: ${response.metadata.sessionId}`);
        setSessionId(response.metadata.sessionId);
      }
    });

    socket.on('chat:error', (data: { messageId: string; error: string; timestamp: string }) => {
      addMessage({
        id: data.messageId,
        role: 'system',
        content: `Error: ${data.error}`,
        timestamp: data.timestamp,
      });
      setLoading(false);
      setPhase(null);
    });

    return () => {
      socket.disconnect();
    };
  }, [addMessage, setLoading, setPhase, setSessionId]);

  const sendMessage = (message: string, options?: { includeCharts?: boolean; maxIterations?: number }) => {
    if (!socketRef.current?.connected) {
      console.error('Socket not connected');
      return;
    }

    // Get current sessionId from store
    const currentSessionId = useChatStore.getState().sessionId;
    
    if (currentSessionId) {
      console.log(`📎 Sending with session ID: ${currentSessionId}`);
    }

    // Add user message to store
    addMessage({
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    });

    // Send to server with sessionId for conversation continuity
    socketRef.current.emit('chat:message', {
      message,
      options: options || {},
      sessionId: currentSessionId,  // Include session ID from client store
    });
  };

  return {
    socket: socketRef.current,
    sendMessage,
    isConnected,
  };
}

