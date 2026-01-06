import { Card, CardContent } from '@/components/ui/card';

interface CalculationCardProps {
  calculation: {
    metric_name: string;
    formatted_value: string;
    value?: number;
    unit?: string;
  };
}

export function CalculationCard({ calculation }: CalculationCardProps) {
  return (
    <Card className="p-3 border-gray-200 hover:border-emerald-300 transition-colors">
      <CardContent className="p-0">
        <div className="text-xs font-medium text-gray-500 mb-1">
          {calculation.metric_name}
        </div>
        <div className="text-lg font-bold text-gray-900">
          {calculation.formatted_value}
        </div>
      </CardContent>
    </Card>
  );
}

