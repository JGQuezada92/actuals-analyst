import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface ProgressCardProps {
  title: string;
  percentage: number;
  subtitle: string;
  detail: string;
  status: 'complete' | 'late' | 'on-track';
  link?: { text: string; href: string };
}

export function ProgressCard({ 
  title, 
  percentage, 
  subtitle, 
  detail,
  status,
  link 
}: ProgressCardProps) {
  const getStatusBadge = () => {
    switch (status) {
      case 'complete':
        return <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100">Complete</Badge>;
      case 'late':
        return <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100">Late</Badge>;
      case 'on-track':
        return <Badge className="bg-blue-100 text-blue-700 hover:bg-blue-100">On Track</Badge>;
    }
  };

  const getProgressColor = () => {
    if (percentage >= 100) return 'bg-emerald-500';
    if (percentage >= 80) return 'bg-emerald-400';
    if (percentage >= 50) return 'bg-amber-400';
    return 'bg-red-400';
  };

  return (
    <div className="p-6 border-r border-gray-100 last:border-r-0">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">{title}</h3>
        {getStatusBadge()}
      </div>
      
      <div className="flex items-baseline gap-1 mb-1">
        <span className="text-4xl font-bold text-gray-900">{percentage}%</span>
      </div>
      
      <p className="text-sm text-gray-500 mb-3">{subtitle}</p>
      
      {/* Progress bar */}
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden mb-2">
        <div 
          className={cn('h-full rounded-full transition-all duration-500', getProgressColor())}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
      
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-600">{detail}</span>
        {link && (
          <a href={link.href} className="text-amber-600 hover:underline">
            {link.text}
          </a>
        )}
      </div>
    </div>
  );
}

