import type { Config } from 'tailwindcss'
export default {
  content: ['./app/**/*.{ts,tsx}'],
  // `amber` is the brand-accent token (legacy name). The brand accent is now a
  // lighter blue (good white-text contrast on the Build button) for the light theme.
  theme: {
    extend: {
      colors: {
        ink: '#0A0B0D',
        amber: '#3B82F6',
        'amber-soft': '#E8F0FF',
        'amber-line': '#D4E2FB',
        nemo: '#76B900',
      },
    },
  },
  plugins: [],
} satisfies Config
