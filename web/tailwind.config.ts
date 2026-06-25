import type { Config } from 'tailwindcss'
export default {
  content: ['./app/**/*.{ts,tsx}'],
  // `amber` is the brand-accent token (legacy name). The brand accent is now blue.
  theme: { extend: { colors: { ink: '#0A0B0D', amber: '#0052FF', nemo: '#76B900' } } },
  plugins: [],
} satisfies Config
