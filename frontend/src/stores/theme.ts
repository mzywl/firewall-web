import { create } from 'zustand';

type Theme = 'light' | 'dark' | 'system';

interface ThemeStore {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export const useThemeStore = create<ThemeStore>((set, get) => ({
  theme: 'system',
  setTheme: (theme) => {
    set({ theme });
    localStorage.setItem('theme', theme);
    applyTheme(theme);
  },
  toggleTheme: () => {
    const current = get().theme;
    const next = current === 'light' ? 'dark' : 'light';
    set({ theme: next });
    localStorage.setItem('theme', next);
    applyTheme(next);
  },
}));

function applyTheme(theme: Theme) {
  const root = window.document.documentElement;
  root.classList.remove('light', 'dark');

  if (theme === 'system') {
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
    root.classList.add(systemTheme);
  } else {
    root.classList.add(theme);
  }
}

// 初始化主题
if (typeof window !== 'undefined') {
  const stored = localStorage.getItem('theme') as Theme | null;
  if (stored) {
    applyTheme(stored);
  } else {
    applyTheme('system');
  }
}
