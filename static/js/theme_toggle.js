document.addEventListener('DOMContentLoaded', function () {
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    const htmlEl = document.documentElement;

    // Función para actualizar la apariencia del botón (texto/ícono)
    function updateButtonAppearance(theme) {
        if (theme === 'dark') {
            themeToggleBtn.innerHTML = 'Modo Claro ☀️'; // O un ícono de sol
            // Si usas íconos de Bootstrap: <i class="bi bi-sun-fill"></i>
        } else {
            themeToggleBtn.innerHTML = 'Modo Oscuro 🌙'; // O un ícono de luna
            // Si usas íconos de Bootstrap: <i class="bi bi-moon-stars-fill"></i>
        }
    }

    // Establecer la apariencia inicial del botón
    updateButtonAppearance(htmlEl.getAttribute('data-bs-theme'));

    themeToggleBtn.addEventListener('click', function () {
        const currentTheme = htmlEl.getAttribute('data-bs-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        htmlEl.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('theme', newTheme); // Guardar la preferencia
        updateButtonAppearance(newTheme);
    });
});