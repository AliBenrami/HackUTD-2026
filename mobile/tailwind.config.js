/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        ink: '#080C12',
        panel: '#111923',
        raised: '#172232',
        cyan: '#00D9E8',
        violet: '#8B5CF6',
        magenta: '#E879F9',
        mist: '#F3F6FA',
        slate: '#8B97A8',
      },
    },
  },
  plugins: [],
};
