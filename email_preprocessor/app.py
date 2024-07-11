import subprocess

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


async def homepage(request):
    command = [
        """bootstrap-email -s '<a href="#" class="btn btn-primary">Some Button</a>'"""
    ]
    result = subprocess.run(command, capture_output=True, text=True, shell=True)
    # Check if the command was successful
    if result.returncode == 0:
        output = result.stdout  # This is the output as a string
    else:
        output = result.stderr

    return JSONResponse({'html': output})


routes = [
    Route("/", endpoint=homepage)
]

app = Starlette(debug=True, routes=routes)
