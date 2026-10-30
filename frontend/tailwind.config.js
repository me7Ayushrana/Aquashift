/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        aquashift: {
          dark: '#0c2826',
          deep: '#134e4a',
          teal: '#0d9488',
          aqua: '#0ea5e9',
          light: '#f0fdfa',
          wheat: '#d97706',
          wheatLight: '#fef3c7',
          wheatDark: '#92400e',
          green: '#166534',
          greenLight: '#dcfce7',
          card: '#113532',
        }
      }
    },
  },
  plugins: [],
}
