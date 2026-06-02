/**
 * Handles system dark/light theme by setting the appropriate data-theme value on the document root.
 */
const rootElement = document.documentElement;
if (rootElement.getAttribute('data-theme').split(/\s+/).includes('system')) {
    // If server sets 'system' (saved pref), then the client will monitor the browser preference
    // and update the root element to trigger the appropriate styles.
    const setSystemTheme = (isDark) => {
        rootElement.setAttribute('data-theme', `system ${isDark ? 'dark' : 'light'}`);
    };
    const isDark = window.matchMedia("(prefers-color-scheme: dark)");
    isDark.addEventListener("change", e => setSystemTheme(e.matches));
    setSystemTheme(isDark.matches);
}
