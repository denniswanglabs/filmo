import type { Config } from 'tailwindcss'
export default {
  content: ['./app/**/*.{ts,tsx}'],
  theme: { extend: { colors: { ink: '#14171C', amber: '#D6351C', nemo: '#76B900' } } },
  plugins: [],
} satisfies Config
