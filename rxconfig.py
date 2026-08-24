import reflex as rx


config = rx.Config(
    app_name="radar_v2",
    frontend_port=3030,
    backend_port=8031,
    api_url="http://127.0.0.1:8031",
    deploy_url="http://localhost:3030",
    telemetry_enabled=False,
    env_file=".env",
    plugins=[
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(appearance="dark", accent_color="orange", gray_color="slate", radius="large", scaling="100%")
        ),
    ],
    disable_plugins=[rx.plugins.SitemapPlugin],
)
