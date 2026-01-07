from fastapi import FastAPI, Form, Request
from dotenv import load_dotenv
from fastapi.responses import HTMLResponse, RedirectResponse
import os
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from utils.graph_generator import generate_pid_graph
from starlette.middleware.sessions import SessionMiddleware
from app import auth
import uuid
from authlib.integrations.starlette_client import OAuth
import json

app = FastAPI()

# Load .env for local development (if present)
load_dotenv()

# Static files and templates initialization
app.mount("/static", StaticFiles(directory="static"), name="static")
# Serve generated images from the output folder
app.mount("/output", StaticFiles(directory="output"), name="output")
templates = Jinja2Templates(directory="templates")

# CORS: Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session middleware for simple cookie-based sessions
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "changeme"))

# OAuth client setup (Google)
oauth = OAuth()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """
    Render the homepage with a form for users to input their instructions.
    """
    user = None
    uid = request.session.get("user_id")
    if uid:
        user = auth.get_user(uid)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.post("/generate-pid")
async def generate_graph(request: Request, instruction: str = Form(...)):
    """
    Generate a PI&D graph and return the corresponding image file.
    """
    filename_base = f"pid_graph_{uuid.uuid4().hex}"

    try:
        # Call the graph generator (saves to output/<filename_base>.png)
        graph_data = generate_pid_graph(instruction, filename_base)
        image_url = f"/output/{filename_base}.png"

        # If user is logged in, offer a save option by including user info
        user = None
        uid = request.session.get("user_id")
        if uid:
            user = auth.get_user(uid)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "image_url": image_url,
                "instruction": instruction,
                "nodes": graph_data.get("nodes"),
                "edges": graph_data.get("edges"),
                "user": user,
                "filename_base": filename_base,
            },
        )
    except Exception as exc:
        # Make sure output dir exists for any partial files
        os.makedirs("output", exist_ok=True)
        error_msg = str(exc)
        return templates.TemplateResponse("index.html", {"request": request, "error": error_msg, "instruction": instruction})


@app.on_event("startup")
def startup():
    # initialize DB
    auth.init_db()


@app.get("/login")
async def oauth_login(request: Request):
    """Start Google OAuth login flow."""
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        return templates.TemplateResponse("index.html", {"request": request, "error": "OAuth not configured"})
    # url_for should reference the callback endpoint name
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth")
async def auth_callback(request: Request):
    """OAuth callback: finalize login and create/get user."""
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        return templates.TemplateResponse("index.html", {"request": request, "error": "OAuth not configured"})
    token = await oauth.google.authorize_access_token(request)
    # Try to get ID token claims (OpenID Connect)
    try:
        user_info = await oauth.google.parse_id_token(request, token)
    except Exception:
        # Fallback to userinfo endpoint
        user_info = await oauth.google.userinfo(token=token)

    provider_id = user_info.get("sub") or user_info.get("id")
    email = user_info.get("email")
    name = user_info.get("name") or user_info.get("preferred_username")
    uid = auth.get_or_create_oauth_user("google", provider_id, email, name)
    request.session["user_id"] = uid
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse(url="/", status_code=303)


@app.post("/save-graph")
async def save_graph(request: Request, filename_base: str = Form(...), instruction: str = Form(None)):
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse(url="/login", status_code=303)
    # Save metadata only (graph file is already written)
    form = await request.form()
    nodes = form.get("nodes")
    edges = form.get("edges")
    auth.save_graph(uid, filename_base + ".png", instruction or "", json_loads(nodes) if nodes else None, json_loads(edges) if edges else None)
    return RedirectResponse(url="/", status_code=303)


def json_loads(s):
    import json
    try:
        return json.loads(s) if s else None
    except Exception:
        return None