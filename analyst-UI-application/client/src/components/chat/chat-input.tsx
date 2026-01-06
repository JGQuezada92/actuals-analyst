import { useState, KeyboardEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send } from 'lucide-react';
import { useSocket } from '@/hooks/use-socket';
import { useChatStore } from '@/stores/chat-store';

export function ChatInput() {
  const [message, setMessage] = useState('');
  const { sendMessage, isConnected } = useSocket();
  const isLoading = useChatStore((state) => state.isLoading);

  const handleSend = () => {
    if (!message.trim() || !isConnected || isLoading) return;
    
    sendMessage(message.trim());
    setMessage('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t p-4">
      <div className="flex gap-2">
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isConnected ? "Ask a question about your financial data..." : "Connecting..."}
          disabled={!isConnected || isLoading}
          className="min-h-[60px] resize-none"
          rows={2}
        />
        <Button
          onClick={handleSend}
          disabled={!message.trim() || !isConnected || isLoading}
          size="icon"
          className="h-[60px] w-[60px]"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
      {!isConnected && (
        <p className="text-xs text-muted-foreground mt-2">
          Connecting to server...
        </p>
      )}
    </div>
  );
}

