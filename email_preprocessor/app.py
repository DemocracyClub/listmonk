import subprocess
from pathlib import Path

import markdown
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

EMAIL_TEMPLATE_PATH = "default_email.html"


async def process_html(request):
    body = await request.json()

    html_content = markdown.markdown(body["markdown"])

    with Path(EMAIL_TEMPLATE_PATH).open() as f:
        html_wrapper = f.read()

    html = html_wrapper.replace("""{{ template "content" . }}""", html_content)

    process = subprocess.Popen(
        ["bootstrap-email"],  # Command to run
        cwd="/tmp/",
        stdin=subprocess.PIPE,  # Connect the stdin pipe
        stdout=subprocess.PIPE,  # Optionally connect the stdout pipe
        stderr=subprocess.PIPE,  # Optionally connect the stderr pipe
        text=True,  # Treat stdin/stdout/stderr as text streams
    )

    # Write data to stdin and close the stdin pipe
    stdout, stderr = process.communicate(input=html)

    # Check if the command was successful
    output = stdout if process.returncode == 0 else stderr

    return JSONResponse(
        {
            "html": output,
            "status": process.returncode,
            "stderr": stderr,
            "stdout": stdout,
        }
    )


async def edit_view(request):
    return templates.TemplateResponse(request, "index.html")


routes = [
    Route(
        "/preprocessor/process_preprocessor",
        endpoint=process_html,
        methods=["POST"],
    ),
    Route("/preprocessor", endpoint=edit_view, methods=["GET"]),
]

app = Starlette(routes=routes)
