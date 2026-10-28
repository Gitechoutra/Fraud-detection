/** Design tokens. Surfaces are CSS variables (see index.css) so light and
 *  dark mode switch by toggling the `dark` class on <html>. */
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        bg: 'rgb(var(--bg) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        surface2: 'rgb(var(--surface-2) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        ink: 'rgb(var(--ink) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        primary: { DEFAULT: '#6366F1', soft: 'rgb(99 102 241 / 0.12)', dark: '#4F46E5' },
        approved: { DEFAULT: '#10B981', soft: 'rgb(16 185 129 / 0.12)' },
        review: { DEFAULT: '#F59E0B', soft: 'rgb(245 158 11 / 0.14)' },
        blocked: { DEFAULT: '#EF4444', soft: 'rgb(239 68 68 / 0.12)' },
      },
      borderRadius: { '2xl': '1rem', '3xl': '1.5rem' },
      boxShadow: {
        soft: '0 1px 2px rgb(15 23 42 / 0.04), 0 8px 24px rgb(15 23 42 / 0.06)',
        glow: '0 0 0 1px rgb(99 102 241 / 0.25), 0 8px 30px rgb(99 102 241 / 0.25)',
      },
    },
  },
  plugins: [],
};
