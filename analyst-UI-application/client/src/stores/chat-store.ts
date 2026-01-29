import { create } from 'zustand';
import { ChatMessage } from '@/types';

interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  currentPhase: string | null;
  sessionId: string | null;  // Track session ID for conversation continuity
  addMessage: (message: ChatMessage) => void;
  setLoading: (loading: boolean) => void;
  setPhase: (phase: string | null) => void;
  setSessionId: (sessionId: string) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isLoading: false,
  currentPhase: null,
  sessionId: null,
  
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
  
  setLoading: (loading) =>
    set({ isLoading: loading }),
  
  setPhase: (phase) =>
    set({ currentPhase: phase }),
  
  setSessionId: (sessionId) =>
    set({ sessionId }),
  
  clearMessages: () =>
    set({ messages: [], isLoading: false, currentPhase: null, sessionId: null }),
}));

