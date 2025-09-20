/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        pokemon: {
          red: '#ff6b6b',
          blue: '#4ecdc4',
          yellow: '#ffe66d',
          darkBlue: '#2c5282',
          lightBlue: '#f0f8ff',
        },
      },
      boxShadow: {
        'pokemon': '0 4px 15px rgba(255, 107, 107, 0.3)',
        'pokemon-hover': '0 6px 20px rgba(78, 205, 196, 0.4)',
      },
    },
  },
  plugins: [],
};