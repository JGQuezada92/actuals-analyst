import { ChatMessage } from '@/types';
import { cn } from '@/lib/utils';
import { User, Bot, AlertCircle, ExternalLink, CheckCircle } from 'lucide-react';
import { CalculationCard } from './calculation-card';
import { AnalysisFormatter } from './analysis-formatter';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Link } from 'react-router-dom';

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isError = message.role === 'system' && message.content.startsWith('Error:');

  return (
    <div className={cn('flex gap-4 mb-6', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center shadow-sm',
          isUser 
            ? 'bg-gradient-to-br from-emerald-500 to-emerald-600 text-white' 
            : 'bg-white border border-gray-200 text-gray-600'
        )}
      >
        {isUser ? <User className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
      </div>

      {/* Content */}
      <div className={cn('flex flex-col max-w-[75%]', isUser ? 'items-end' : 'items-start')}>
        {/* Sender name */}
        <span className="text-xs font-medium text-gray-500 mb-1 px-1">
          {isUser ? 'You' : 'Financial Analyst'}
        </span>
        
        {/* Message bubble */}
        <Card
          className={cn(
            'shadow-sm',
            isUser
              ? 'bg-emerald-600 text-white border-emerald-600 px-4 py-3'
              : 'bg-white border-gray-200 p-0',
            isError && 'bg-red-50 border-red-200 text-red-700 px-4 py-3'
          )}
        >
          {isError && (
            <div className="flex items-center gap-2 mb-2 text-red-600">
              <AlertCircle className="h-4 w-4" />
              <span className="font-medium">Error</span>
            </div>
          )}
          
          {isError ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {message.content.replace('Error: ', '')}
            </p>
          ) : isUser ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {message.content}
            </p>
          ) : (
            <div className="p-5">
              <AnalysisFormatter content={message.content} />
            </div>
          )}
        </Card>

        {/* Calculations */}
        {message.metadata?.calculations && message.metadata.calculations.length > 0 && (
          <div className="w-full mt-3 space-y-2">
            <p className="text-xs font-medium text-gray-500 px-1">Calculations</p>
            <div className="grid grid-cols-2 gap-2">
              {message.metadata.calculations.slice(0, 4).map((calc, i) => (
                <CalculationCard key={i} calculation={calc} />
              ))}
            </div>
            {message.metadata.calculations.length > 4 && (
              <Button variant="ghost" size="sm" className="text-gray-500">
                +{message.metadata.calculations.length - 4} more calculations
              </Button>
            )}
          </div>
        )}

        {/* Charts */}
        {message.metadata?.charts && message.metadata.charts.length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium text-gray-500 px-1">Charts</p>
            <div className="flex flex-wrap gap-2">
              {message.metadata.charts.map((chart, i) => (
                <Card key={i} className="overflow-hidden">
                  <img
                    src={`data:image/png;base64,${chart}`}
                    alt={`Chart ${i + 1}`}
                    className="max-w-sm"
                  />
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center gap-3 mt-2 px-1">
          <span className="text-xs text-gray-400">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
          
          {message.metadata?.evaluation && (
            <Badge
              variant="outline"
              className={cn(
                'text-xs',
                message.metadata.evaluation.passed_evaluation
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-gray-200 bg-gray-50 text-gray-600'
              )}
            >
              {message.metadata.evaluation.passed_evaluation && (
                <CheckCircle className="h-3 w-3 mr-1" />
              )}
              Score: {message.metadata.evaluation.qualitative_score?.toFixed(1)}
            </Badge>
          )}

          {message.metadata?.traceId && (
            <Button 
              variant="ghost" 
              size="sm" 
              asChild 
              className="h-6 px-2 text-xs text-gray-500 hover:text-emerald-600"
            >
              <Link to={`/traces/${message.metadata.traceId}`}>
                <ExternalLink className="h-3 w-3 mr-1" />
                View Trace
              </Link>
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
