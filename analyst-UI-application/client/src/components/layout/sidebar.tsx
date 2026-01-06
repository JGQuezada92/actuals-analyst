import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  MessageSquare,
  BarChart3,
  Settings,
  Activity,
  Home,
  LogOut,
  User,
  HelpCircle,
  MessageCircle,
  ExternalLink,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';

const mainNavigation = [
  { name: 'Dashboard', href: '/admin', icon: Home, color: 'text-gray-600' },
  { name: 'Chat', href: '/', icon: MessageSquare, color: 'text-emerald-600' },
  { name: 'Traces', href: '/traces', icon: Activity, color: 'text-amber-600' },
  { name: 'Analytics', href: '/admin', icon: BarChart3, color: 'text-blue-600' },
];

const bottomNavigation = [
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const location = useLocation();

  return (
    <div className="flex flex-col h-full w-16 bg-white border-r border-gray-200">
      {/* Logo */}
      <div className="flex items-center justify-center h-16 border-b border-gray-100">
        <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-lg">FA</span>
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 flex flex-col items-center py-4 space-y-2">
        {mainNavigation.map((item) => {
          const isActive = location.pathname === item.href ||
            (item.href !== '/' && location.pathname.startsWith(item.href));
          
          return (
            <Link
              key={item.name}
              to={item.href}
              className={cn(
                'group relative flex items-center justify-center w-12 h-12 rounded-xl transition-all duration-200',
                isActive
                  ? 'bg-emerald-50 text-emerald-600'
                  : 'text-gray-400 hover:bg-gray-50 hover:text-gray-600'
              )}
            >
              <item.icon className={cn(
                'h-6 w-6 transition-colors',
                isActive ? 'text-emerald-600' : item.color
              )} />
              
              {/* Active indicator */}
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-emerald-500 rounded-r-full" />
              )}
              
              {/* Tooltip */}
              <div className="absolute left-full ml-3 px-3 py-2 bg-gray-900 text-white text-sm rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50">
                {item.name}
                <div className="absolute right-full top-1/2 -translate-y-1/2 border-8 border-transparent border-r-gray-900" />
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Bottom Navigation */}
      <div className="flex flex-col items-center py-4 space-y-2 border-t border-gray-100">
        {bottomNavigation.map((item) => (
          <Link
            key={item.name}
            to={item.href}
            className="group relative flex items-center justify-center w-12 h-12 rounded-xl text-gray-400 hover:bg-gray-50 hover:text-gray-600 transition-all duration-200"
          >
            <item.icon className="h-6 w-6" />
            <div className="absolute left-full ml-3 px-3 py-2 bg-gray-900 text-white text-sm rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50">
              {item.name}
            </div>
          </Link>
        ))}

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center justify-center w-12 h-12 rounded-xl hover:bg-gray-50 transition-all duration-200">
              <Avatar className="h-9 w-9 border-2 border-emerald-200">
                <AvatarFallback className="bg-emerald-100 text-emerald-700 font-semibold">
                  JQ
                </AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent 
            side="right" 
            align="end" 
            className="w-64 p-2"
            sideOffset={12}
          >
            <div className="px-3 py-3 border-b border-gray-100 mb-2">
              <div className="flex items-center gap-3">
                <Avatar className="h-10 w-10">
                  <AvatarFallback className="bg-emerald-100 text-emerald-700 font-semibold">
                    JQ
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-900 truncate">Jonathan Quezada</p>
                  <p className="text-sm text-gray-500 truncate">jonathan.quezada@phenom...</p>
                </div>
              </div>
            </div>
            <DropdownMenuItem className="py-2.5 px-3 cursor-pointer">
              <User className="h-4 w-4 mr-3 text-gray-400" />
              Profile Settings
            </DropdownMenuItem>
            <DropdownMenuItem className="py-2.5 px-3 cursor-pointer">
              <HelpCircle className="h-4 w-4 mr-3 text-gray-400" />
              Help Center
              <ExternalLink className="h-3 w-3 ml-auto text-gray-400" />
            </DropdownMenuItem>
            <DropdownMenuItem className="py-2.5 px-3 cursor-pointer">
              <MessageCircle className="h-4 w-4 mr-3 text-gray-400" />
              Customer Feedback
              <ExternalLink className="h-3 w-3 ml-auto text-gray-400" />
            </DropdownMenuItem>
            <DropdownMenuSeparator className="my-2" />
            <DropdownMenuItem className="py-2.5 px-3 cursor-pointer text-gray-600">
              <LogOut className="h-4 w-4 mr-3 text-gray-400" />
              Sign Out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
