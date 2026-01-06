import { useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { useChatStore } from '@/stores/chat-store';
import { ChatMessage, AgentResponse } from '@/types';

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:3001';

export function useSocket() {
  const socketRef = useRef<Socket | null>(null);
  const { addMessage, setLoading, setPhase } = useChatStore();

  useEffect(() => {
    // Initialize socket
    socketRef.current = io(SOCKET_URL, {
      transports: ['websocket'],
    });

    const socket = socketRef.current;

    socket.on('connect', () => {
      console.log('✅ Connected to server');
    });

    socket.on('disconnect', () => {
      console.log('❌ Disconnected from server');
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
  }, [addMessage, setLoading, setPhase]);

  const sendMessage = (message: string, options?: { includeCharts?: boolean; maxIterations?: number }) => {
    if (!socketRef.current?.connected) {
      console.error('Socket not connected');
      return;
    }

    // Add user message to store
    addMessage({
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    });

    // Send to server
    socketRef.current.emit('chat:message', {
      message,
      options: options || {},
    });
  };

  return {
    socket: socketRef.current,
    sendMessage,
    isConnected: socketRef.current?.connected || false,
  };
}

