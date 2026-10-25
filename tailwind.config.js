/** Configuración de Tailwind. El CSS compilado queda en static/tailwind.css */
module.exports = {
  content: ["./index.html", "./admin.html"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Bricolage Grotesque"', "system-ui", "sans-serif"] },
      colors: {
        bosque: "#14342b", // verde oscuro: cabecera y botón principal
        hoja: "#2f9e5b",   // verde de la caneca de orgánicos
        tiza: "#f2f5f3",   // fondo general
      },
    },
  },
};
