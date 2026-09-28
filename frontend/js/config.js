// URL base de la API: local en desarrollo, Render en producción.
window.APP_CONFIG = {
    API_URL: ["localhost", "127.0.0.1"].includes(location.hostname)
        ? "http://localhost:8000"
        : "https://motor-horarios-oci-1.onrender.com",
};
