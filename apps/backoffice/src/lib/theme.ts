// Tema (claro/oscuro/sistema) y densidad (normal/compacta) del backoffice, por navegador.
export type Theme = 'light' | 'dark' | 'system';
export type Density = 'normal' | 'compact';
const K_THEME = 'pepito.backoffice.theme';
const K_DENSITY = 'pepito.backoffice.density';

function read(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

export function getTheme(): Theme {
  return read(K_THEME, 'system') as Theme;
}
export function getDensity(): Density {
  return read(K_DENSITY, 'normal') as Density;
}

export function applyTheme(theme: Theme = getTheme(), density: Density = getDensity()): void {
  const root = document.documentElement;
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches);
  root.setAttribute('data-theme', dark ? 'dark' : 'light');
  root.setAttribute('data-density', density);
}

export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(K_THEME, theme);
  } catch {
    /* modo privado */
  }
  applyTheme(theme);
}
export function setDensity(density: Density): void {
  try {
    localStorage.setItem(K_DENSITY, density);
  } catch {
    /* modo privado */
  }
  applyTheme(getTheme(), density);
}
