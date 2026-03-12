import { Moon, Sun } from 'lucide-react';
import { useThemeStore } from '../../stores/theme';
import { Button } from '../ui/Button';

export const Header = () => {
  const { theme, toggleTheme } = useThemeStore();

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-lg">F</span>
            </div>
            <div>
              <h1 className="text-xl font-bold">防火墙策略管理</h1>
              <p className="text-xs text-muted-foreground">Firewall Policy Management</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            title="切换主题"
          >
            {theme === 'dark' ? (
              <Sun className="h-5 w-5" />
            ) : (
              <Moon className="h-5 w-5" />
            )}
          </Button>
        </div>
      </div>
    </header>
  );
};
