import { useChatStore } from '@/stores/chat-store';
import { MessageBubble } from './message-bubble';
import { useEffect, useRef } from 'react';
import { Bot } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

export function MessageList() {
  const messages = useChatStore((state) => state.messages);
  const currentPhase = useChatStore((state) => state.currentPhase);
  const isLoading = useChatStore((state) => state.isLoading);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading, currentPhase]);

  return (
    <div className="space-y-4" ref={scrollRef}>
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      
      {isLoading && (
        <div className="flex gap-3">
          <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-white border border-gray-200 flex items-center justify-center">
            <Bot className="h-5 w-5 text-gray-600" />
          </div>
          <Card className="bg-white border-gray-200">
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-emerald-600"></div>
                <span className="text-sm text-gray-600">
                  {currentPhase || 'Analyzing...'}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
