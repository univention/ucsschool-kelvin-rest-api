import json

from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import swagger_ui_default_parameters
from starlette.responses import HTMLResponse

SWAGGER_JS_CDN_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
SWAGGER_PRESET_JS_CDN_URL = (
    "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"
)
SWAGGER_CSS_CDN_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
FAVICON_URL = "https://fastapi.tiangolo.com/img/favicon.png"


def get_swagger_ui_html(
    *,
    openapi_urls,
    title,
    swagger_js_url=SWAGGER_JS_CDN_URL,
    swagger_preset_js_url=SWAGGER_PRESET_JS_CDN_URL,
    swagger_css_url=SWAGGER_CSS_CDN_URL,
    swagger_favicon_url=FAVICON_URL,
    oauth2_redirect_url=None,
    init_oauth=None,
    swagger_ui_parameters=None,
) -> HTMLResponse:
    """
    Workaround for fastapi.docs.get_swagger_ui_html, see:
    https://github.com/fastapi/fastapi/discussions/14340
    """
    current_swagger_ui_parameters = swagger_ui_default_parameters.copy()
    if swagger_ui_parameters:
        current_swagger_ui_parameters.update(swagger_ui_parameters)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <link type="text/css" rel="stylesheet" href="{swagger_css_url}">
    <link rel="shortcut icon" href="{swagger_favicon_url}">
    <title>{title}</title>
    </head>
    <body>
    <div id="swagger-ui">
    </div>
    <script src="{swagger_js_url}"></script>
    <script src="{swagger_preset_js_url}"></script>
    <!-- `SwaggerUIBundle` is now available on the page -->
    <script>
    const ui = SwaggerUIBundle({{
        urls: {json.dumps(openapi_urls)},
    """

    for key, value in current_swagger_ui_parameters.items():
        html += f"{json.dumps(key)}: {json.dumps(jsonable_encoder(value))},\n"

    if oauth2_redirect_url:
        html += f"oauth2RedirectUrl: window.location.origin + '{oauth2_redirect_url}',"

    html += """
    presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIStandalonePreset
        ],
    })"""

    if init_oauth:
        html += f"""
        ui.initOAuth({json.dumps(jsonable_encoder(init_oauth))})
        """

    html += """
    </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
