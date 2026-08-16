/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Pulled from codespace.co.za, not the generic indigo/slate the
        // board started with -- see docs/BUILD_NOTES.md (F6) for how these
        // were sourced.
        codespace: {
          teal: '#3F9C8C',
          tealDark: '#337F72',
          mint: '#DCF2EA',
          ink: '#1A1A1A',
          gray: '#F2F2F0',
          coral: '#E2734A',
        },
      },
    },
  },
  plugins: [],
}