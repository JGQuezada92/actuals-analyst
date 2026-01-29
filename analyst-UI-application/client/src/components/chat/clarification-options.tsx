import { Badge } from '@/components/ui/badge';
import { HelpCircle, ChevronRight, Sparkles } from 'lucide-react';
import { ClarificationData } from '@/types';
import { cn } from '@/lib/utils';

interface ClarificationOptionsProps {
  clarification: ClarificationData;
  onSelectOption: (optionValue: string) => void;
  disabled?: boolean;
}

export function ClarificationOptions({ 
  clarification, 
  onSelectOption,
  disabled = false 
}: ClarificationOptionsProps) {
  return (
    <div className="space-y-4">
      {/* Header with question context */}
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center">
          <HelpCircle className="h-4 w-4 text-amber-600" />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-gray-900 mb-1">
            Clarification Needed
          </h4>
          <p className="text-sm text-gray-600 leading-relaxed">
            {clarification.clarificationMessage}
          </p>
        </div>
      </div>

      {/* Ambiguous terms badges */}
      {clarification.ambiguousTerms && clarification.ambiguousTerms.length > 0 && (
        <div className="flex flex-wrap gap-2 pl-11">
          {clarification.ambiguousTerms.map((term, idx) => (
            <Badge 
              key={idx} 
              variant="outline" 
              className="bg-amber-50 border-amber-200 text-amber-700"
            >
              <Sparkles className="h-3 w-3 mr-1" />
              {term}
            </Badge>
          ))}
        </div>
      )}

      {/* Options as clickable bubbles */}
      <div className="space-y-2 pl-11">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
          Select an option:
        </p>
        
        <div className="grid gap-2">
          {clarification.options.map((option) => (
            <button
              key={option.id}
              onClick={() => onSelectOption(option.value)}
              disabled={disabled}
              className={cn(
                "group relative w-full text-left p-4 rounded-xl border-2 transition-all duration-200",
                "hover:border-emerald-400 hover:bg-emerald-50/50 hover:shadow-md",
                "focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2",
                "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-gray-200 disabled:hover:bg-white disabled:hover:shadow-none",
                "bg-white border-gray-200"
              )}
            >
              <div className="flex items-start gap-3">
                {/* Option number bubble */}
                <div className={cn(
                  "flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold transition-colors",
                  "bg-gray-100 text-gray-600 group-hover:bg-emerald-500 group-hover:text-white"
                )}>
                  {option.id}
                </div>
                
                {/* Option content */}
                <div className="flex-1 min-w-0">
                  <h5 className="text-sm font-semibold text-gray-900 group-hover:text-emerald-700 transition-colors">
                    {option.label}
                  </h5>
                  {option.description && (
                    <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                      {option.description}
                    </p>
                  )}
                </div>
                
                {/* Arrow indicator */}
                <ChevronRight className={cn(
                  "flex-shrink-0 h-5 w-5 text-gray-300 transition-all",
                  "group-hover:text-emerald-500 group-hover:translate-x-1"
                )} />
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Or type custom response hint */}
      <div className="pl-11 pt-2">
        <p className="text-xs text-gray-400 italic">
          Or type your own clarification in the message box below
        </p>
      </div>
    </div>
  );
}
