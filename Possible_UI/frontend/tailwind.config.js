/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      spacing: {
        4.5: '1.125rem',
        5.5: '1.375rem',
      },
      colors: {
        // Deep enterprise navy used for the sidebar / chrome
        navy: {
          50: '#eef2f9',
          900: '#0a1729',
          850: '#0d1d33',
          800: '#10233e',
          700: '#16304f',
          600: '#1e3d63',
          500: '#2c4f7c',
        },
        // Soft blue brand accent
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgba(16, 35, 62, 0.04), 0 1px 3px 0 rgba(16, 35, 62, 0.08)',
        cardhover: '0 4px 12px -2px rgba(16, 35, 62, 0.12), 0 2px 6px -2px rgba(16, 35, 62, 0.08)',
        panel: '0 8px 30px -8px rgba(10, 23, 41, 0.16)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        'pulse-soft': 'pulse-soft 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
