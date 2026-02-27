/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
                outfit: ['Outfit', 'sans-serif'],
            },
            colors: {
                dark: {
                    DEFAULT: '#050505',
                    soft: '#0a0a0a',
                    accent: '#1a1a1a',
                },
                aethelgard: {
                    green: '#00ff41', // Matrix/Hacker green
                    blue: '#00d2ff',
                    cyan: '#00f2ff', // Cian Neón
                    purple: '#9d50bb',
                    gold: '#cba135',
                    red: '#ff0055',  // Rojo Alerta
                }
            }
        },
    },
    plugins: [],
}
