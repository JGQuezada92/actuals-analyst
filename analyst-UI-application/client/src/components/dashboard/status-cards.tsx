import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface StatusCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  status: 'success' | 'warning' | 'info' | 'neutral';
  link?: { text: string; href: string };
}

const statusStyles = {
  success: {
    dot: 'bg-emerald-500',
    text: 'text-emerald-600',
    label: 'text-emerald-600',
  },
  warning: {
    dot: 'bg-amber-500',
    text: 'text-amber-600',
    label: 'text-amber-600',
  },
  info: {
    dot: 'bg-blue-500',
    text: 'text-blue-600',
    label: 'text-blue-600',
  },
  neutral: {
    dot: 'bg-gray-400',
    text: 'text-gray-600',
    label: 'text-gray-600',
  },
};

export function StatusCard({ title, value, subtitle, status, link }: StatusCardProps) {
  const styles = statusStyles[status];

  return (
    <div className="flex flex-col items-center p-6">
      <div className="flex items-center gap-2 mb-3">
        <div className={cn('w-3 h-3 rounded-full', styles.dot)} />
        <span className="text-sm font-medium text-gray-600">{title}</span>
      </div>
      <span className={cn('text-5xl font-bold', styles.text)}>{value}</span>
      {subtitle && (
        <span className="text-sm text-gray-500 mt-1">{subtitle}</span>
      )}
      {link && (
        <a href={link.href} className={cn('text-sm mt-2 hover:underline', styles.label)}>
          {link.text}
        </a>
      )}
    </div>
  );
}

export function StatusCardsRow({ children }: { children: React.ReactNode }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="bg-gray-50 border-b border-gray-200 py-3 px-4">
        <CardTitle className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Sign-offs by Status
          <span className="text-gray-400 font-normal ml-2">(114 Total)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid grid-cols-3 divide-x divide-gray-100">
          {children}
        </div>
      </CardContent>
    </Card>
  );
}

