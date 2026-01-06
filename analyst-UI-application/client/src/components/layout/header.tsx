import { useLocation } from 'react-router-dom';
import { Moon, Sun, HelpCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTheme } from '@/components/theme-provider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

const pageConfig: Record<string, { title: string; tabs?: string[] }> = {
  '/': { title: 'Financial Analyst', tabs: ['Chat'] },
  '/admin': { title: 'Dashboard', tabs: ['Overview', 'Timeline', 'Entities'] },
  '/traces': { title: 'Traces', tabs: ['All Traces', 'Errors', 'Slow Queries'] },
  '/settings': { title: 'Settings' },
};

export function Header() {
  const location = useLocation();
  const { theme, setTheme } = useTheme();
  
  const config = pageConfig[location.pathname] || { title: 'Financial Analyst' };

  return (
    <header className="bg-white border-b border-gray-200">
      {/* Top bar */}
      <div className="flex items-center justify-between h-14 px-6">
        <div className="flex items-center gap-6">
          {/* Entity Selector (like FloQast's "Phenom People Inc") */}
          <Select defaultValue="default">
            <SelectTrigger className="w-[200px] border-gray-200 bg-white">
              <SelectValue placeholder="Select entity" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">Phenom People Inc</SelectItem>
              <SelectItem value="subsidiary1">Subsidiary 1</SelectItem>
              <SelectItem value="subsidiary2">Subsidiary 2</SelectItem>
            </SelectContent>
          </Select>

          {/* Period Selector */}
          <Select defaultValue="current">
            <SelectTrigger className="w-[160px] border-gray-200 bg-white">
              <SelectValue placeholder="Select period" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="current">January 2026</SelectItem>
              <SelectItem value="dec2025">December 2025</SelectItem>
              <SelectItem value="nov2025">November 2025</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          {/* Theme Toggle */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="text-gray-400 hover:text-gray-600"
          >
            {theme === 'dark' ? (
              <Sun className="h-5 w-5" />
            ) : (
              <Moon className="h-5 w-5" />
            )}
          </Button>
          
          {/* Help */}
          <Button variant="ghost" size="icon" className="text-gray-400 hover:text-gray-600">
            <HelpCircle className="h-5 w-5" />
          </Button>
        </div>
      </div>

      {/* Tabs bar (like FloQast's Overview/Timeline/Entities) */}
      {config.tabs && (
        <div className="flex items-center gap-8 px-6 border-t border-gray-100">
          {config.tabs.map((tab, index) => (
            <button
              key={tab}
              className={cn(
                'relative py-3 text-sm font-medium transition-colors',
                index === 0
                  ? 'text-emerald-600'
                  : 'text-gray-500 hover:text-gray-700'
              )}
            >
              {tab}
              {index === 0 && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" />
              )}
            </button>
          ))}
        </div>
      )}
    </header>
  );
}
