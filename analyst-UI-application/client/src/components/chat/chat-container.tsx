import { useRef, useEffect } from 'react';
import { useChatStore } from '@/stores/chat-store';
import { useSocket } from '@/hooks/use-socket';
import { MessageList } from './message-list';
import { ChatInput } from './chat-input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Trash2, RefreshCw, Wifi, WifiOff, Filter } from 'lucide-react';
import { cn } from '@/lib/utils';

export function ChatContainer() {
  const { messages, isLoading, clearMessages } = useChatStore();
  const { isConnected } = useSocket();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Page Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Financial Analyst</h1>
            <p className="text-sm text-gray-500 mt-1">
              Ask questions about your NetSuite financial data
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Connection Status */}
            <div className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-full text-sm',
              isConnected 
                ? 'bg-emerald-50 text-emerald-700' 
                : 'bg-gray-100 text-gray-500'
            )}>
              {isConnected ? (
                <>
                  <Wifi className="h-4 w-4" />
                  <span>Connected</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-4 w-4" />
                  <span>Connecting...</span>
                </>
              )}
            </div>
            
            {/* Filter Button */}
            <Button variant="outline" className="gap-2">
              <Filter className="h-4 w-4" />
              Filter
            </Button>
            
            {/* Clear Button */}
            <Button 
              variant="ghost" 
              onClick={clearMessages}
              className="text-gray-500 hover:text-gray-700"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Clear Chat
            </Button>
          </div>
        </div>
        
        {/* Last Updated */}
        <div className="flex items-center justify-end mt-2 text-sm text-gray-400">
          <span>Last Updated: {new Date().toLocaleString()}</span>
          <Button variant="link" className="text-emerald-600 p-0 ml-2 h-auto">
            <RefreshCw className="h-3 w-3 mr-1" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Chat Messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-6"
      >
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <MessageList />
        )}
      </div>

      {/* Input Area */}
      <div className="bg-white border-t border-gray-200 p-4">
        <div className="max-w-4xl mx-auto">
          <ChatInput />
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full py-12">
      <div className="w-20 h-20 bg-emerald-100 rounded-2xl flex items-center justify-center mb-6">
        <span className="text-4xl">📊</span>
      </div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">
        Welcome to Financial Analyst
      </h2>
      <p className="text-gray-500 text-center max-w-md mb-8">
        Ask questions about your NetSuite financial data and get instant insights
      </p>
      
      {/* Example queries */}
      <div className="space-y-3 w-full max-w-lg">
        <p className="text-sm font-medium text-gray-500 text-center mb-4">
          Try asking:
        </p>
        {[
          'What are our total expenses YTD?',
          'Show me G&A expenses by department',
          'What\'s the expense trend over the past 6 months?',
        ].map((query, i) => (
          <Card 
            key={i}
            className="p-4 hover:bg-gray-50 cursor-pointer transition-colors border-gray-200"
          >
            <p className="text-gray-700">{query}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
