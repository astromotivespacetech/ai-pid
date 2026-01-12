from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import JSONResponse
from starlette.responses import Response
from dotenv import load_dotenv
from fastapi.responses import HTMLResponse, RedirectResponse
import os
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from utils.graph_generator import generate_pid_graph
from starlette.middleware.sessions import SessionMiddleware
from app import auth
import uuid
from authlib.integrations.starlette_client import OAuth
import json
import shutil
from pathlib import Path


# Custom JSON encoder to handle Undefined and other edge cases
class SafeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # Handle any object that's not JSON serializable
        if hasattr(obj, '__dict__'):
            return self.default(obj.__dict__)
        # For any other non-serializable type, convert to string
        return str(obj)


def json_response(payload: dict, status_code: int = 200) -> Response:
    """Return a JSON HTTP response using a safe encoder (avoids Undefined issues)."""
    try:
        content = json.dumps(payload, cls=SafeJSONEncoder)
    except Exception as e:
        # As a last resort, stringify the payload
        print(f"[json_response] Serialization error: {type(e).__name__}: {e}")
        try:
            content = json.dumps({"error": str(e), "payload": str(payload)})
        except Exception:
            content = '{"error":"serialization failed"}'
    return Response(content=content, media_type="application/json", status_code=status_code)


def deep_clean_for_json(obj, depth=0, max_depth=10):
    """Recursively clean an object to make it JSON-serializable."""
    if depth > max_depth:
        return str(obj)
    
    # Handle None
    if obj is None:
        return None
    
    # Handle primitives
    if isinstance(obj, (bool, int, float, str)):
        return obj
    
    # Handle lists/tuples
    if isinstance(obj, (list, tuple)):
        return [deep_clean_for_json(item, depth + 1, max_depth) for item in obj]
    
    # Handle sets
    if isinstance(obj, set):
        return [deep_clean_for_json(item, depth + 1, max_depth) for item in obj]
    
    # Handle dicts
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            try:
                result[str(key)] = deep_clean_for_json(value, depth + 1, max_depth)
            except Exception as e:
                print(f"[Clean] Error cleaning dict value for key {key}: {e}")
                result[str(key)] = str(value)
        return result
    
    # For any other type, convert to string
    print(f"[Clean] Converting {type(obj).__name__} to string")
    return str(obj)

app = FastAPI()

# Load .env for local development (if present)
load_dotenv()

# Create custom symbols directory if it doesn't exist
CUSTOM_SYMBOLS_DIR = Path("static/symbols/custom")
CUSTOM_SYMBOLS_DIR.mkdir(parents=True, exist_ok=True)

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

# Middleware to handle HTTPS scheme from Railway proxy
class SchemeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("x-forwarded-proto") == "https":
            request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(SchemeMiddleware)

# Session middleware for simple cookie-based sessions
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "changeme"), same_site="lax", https_only=False, max_age=60*60*24*7)

# OAuth client setup (Google, GitHub)
oauth = OAuth()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET:
    oauth.register(
        name="github",
        client_id=GITHUB_CLIENT_ID,
        client_secret=GITHUB_CLIENT_SECRET,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )

PROVIDERS = {
    "google": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
    "github": bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET),
}


def index_context(request: Request, **kwargs):
    ctx = {"request": request, "providers": PROVIDERS}
    ctx.update(kwargs)
    return ctx


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """
    Render the homepage with a form for users to input their instructions.
    """
    user = None
    uid = request.session.get("user_id")
    print(f"[Homepage] Session: {dict(request.session)}, user_id={uid}")
    if uid:
        user = auth.get_user(uid)
        print(f"[Homepage] User: {user}")
    return templates.TemplateResponse("index.html", index_context(request, user=user))


@app.get("/demo", response_class=HTMLResponse)
async def demo(request: Request):
    """
    Load a demo P&ID diagram without requiring login.
    """
    # Sample cooling system diagram
    sample_instruction = "Cooling water system: Centrifugal pump takes water from reservoir, feeds through pressure relief valve to shell-and-tube heat exchanger, then through check valve to storage tank with level indicator"
    
    sample_nodes = [
        "Pump",
        "Pressure Relief Valve",
        "Heat Exchanger",
        "Check Valve",
        "Storage Tank",
        "Level Indicator"
    ]
    
    sample_edges = [
        ["Pump", "Pressure Relief Valve"],
        ["Pressure Relief Valve", "Heat Exchanger"],
        ["Heat Exchanger", "Check Valve"],
        ["Check Valve", "Storage Tank"],
        ["Storage Tank", "Level Indicator"]
    ]
    
    return templates.TemplateResponse("index.html", index_context(
        request,
        user=None,
        is_demo=True,
        instruction=sample_instruction,
        nodes=sample_nodes,
        edges=sample_edges,
        filename_base="demo_pid"
    ))


@app.post("/generate-pid")
async def generate_graph(request: Request, instruction: str = Form(...), existing_nodes: str = Form(None), existing_edges: str = Form(None)):
    """
    Generate a PI&D graph and return the corresponding image file.
    """
    filename_base = f"pid_graph_{uuid.uuid4().hex}"

    try:
        # Parse existing graph if provided
        existing_graph = None
        if existing_nodes or existing_edges:
            def _safe_json_load(val):
                if not val:
                    return []
                txt = val.strip()
                if not txt:
                    return []
                try:
                    return json.loads(txt)
                except Exception:
                    return []
            existing_graph = {
                "nodes": _safe_json_load(existing_nodes),
                "edges": _safe_json_load(existing_edges)
            }
        
        # Call the graph generator (now returns data only; no image rendering)
        graph_data = generate_pid_graph(instruction, filename_base, existing_graph=existing_graph)
        image_url = None
        if graph_data.get("graph_file"):
            image_url = f"/output/{filename_base}.png"

        # If user is logged in, offer a save option by including user info
        user = None
        uid = request.session.get("user_id")
        if uid:
            user = auth.get_user(uid)
        return templates.TemplateResponse(
            "index.html",
            index_context(
                request,
                image_url=image_url,
                instruction=instruction,
                nodes=graph_data.get("nodes"),
                edges=graph_data.get("edges"),
                user=user,
                filename_base=filename_base,
            ),
        )
    except Exception as exc:
        # Make sure output dir exists for any partial files
        os.makedirs("output", exist_ok=True)
        error_msg = str(exc)
        return templates.TemplateResponse("index.html", index_context(request, error=error_msg, instruction=instruction))


@app.on_event("startup")
def startup():
    # initialize DB
    auth.init_db()


@app.get("/login")
async def oauth_login_default(request: Request):
    """Start OAuth login flow (default: Google)."""
    return await start_oauth(request, "google")


@app.get("/login/{provider}")
async def oauth_login_provider(request: Request, provider: str):
    """Start OAuth login flow for a specific provider."""
    return await start_oauth(request, provider)


async def start_oauth(request: Request, provider: str):
    provider = provider.lower()
    if provider == "google":
        if not PROVIDERS["google"]:
            return templates.TemplateResponse("index.html", index_context(request, error="Google OAuth not configured"))
        redirect_uri = request.url_for("auth_callback", provider="google")
        return await oauth.google.authorize_redirect(request, redirect_uri)
    if provider == "github":
        if not PROVIDERS["github"]:
            return templates.TemplateResponse("index.html", index_context(request, error="GitHub OAuth not configured"))
        redirect_uri = request.url_for("auth_callback", provider="github")
        return await oauth.github.authorize_redirect(request, redirect_uri)
    return templates.TemplateResponse("index.html", index_context(request, error="Unsupported login provider"))


@app.get("/auth/{provider}")
async def auth_callback(request: Request, provider: str):
    """OAuth callback: finalize login and create/get user for the provider."""
    provider = provider.lower()

    try:
        if provider == "google":
            if not PROVIDERS["google"]:
                return templates.TemplateResponse("index.html", index_context(request, error="Google OAuth not configured"))
            token = await oauth.google.authorize_access_token(request)
            try:
                user_info = await oauth.google.parse_id_token(request, token)
            except Exception:
                user_info = await oauth.google.userinfo(token=token)

            provider_id = user_info.get("sub") or user_info.get("id")
            email = user_info.get("email")
            name = user_info.get("name") or user_info.get("preferred_username")
        elif provider == "github":
            if not PROVIDERS["github"]:
                return templates.TemplateResponse("index.html", index_context(request, error="GitHub OAuth not configured"))
            token = await oauth.github.authorize_access_token(request)
            user_resp = await oauth.github.get("user", token=token)
            user_info = user_resp.json() if user_resp else {}

            provider_id = str(user_info.get("id")) if user_info else None
            email = user_info.get("email") if user_info else None
            name = user_info.get("name") or user_info.get("login") if user_info else None

            if not email:
                emails_resp = await oauth.github.get("user/emails", token=token)
                if emails_resp:
                    emails_data = emails_resp.json()
                    if isinstance(emails_data, list) and emails_data:
                        primary = next((e for e in emails_data if e.get("primary") and e.get("verified")), None)
                        fallback = emails_data[0]
                        email = (primary or fallback).get("email")
        else:
            return templates.TemplateResponse("index.html", index_context(request, error="Unsupported login provider"))

        print(f"[OAuth] Provider={provider}, provider_id={provider_id}, email={email}, name={name}")

        uid = auth.get_or_create_oauth_user(provider, provider_id, email, name)

        if uid is None:
            print("[OAuth ERROR] Failed to create/get user")
            return templates.TemplateResponse("index.html", index_context(request, error="Failed to create user account"))

        print(f"[OAuth] Setting session user_id={uid}")
        request.session["user_id"] = uid
        print(f"[OAuth] Session after set: {dict(request.session)}")

        # Check if user has any saved graphs
        user_graphs = auth.get_graphs_for_user(uid)
        
        if user_graphs:
            # Load the most recent graph (assumes graphs are ordered by created_at desc)
            most_recent = user_graphs[0]
            print(f"[OAuth] User has {len(user_graphs)} graph(s), loading most recent: {most_recent['id']}")
            return RedirectResponse(url=f"/load-graph/{most_recent['id']}", status_code=303)
        else:
            # New user with no graphs - go to homepage with blank chat
            print(f"[OAuth] User has no graphs, redirecting to homepage")
            return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        print(f"[OAuth ERROR] {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("index.html", index_context(request, error=f"Login failed: {str(e)}"))


@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse(url="/", status_code=303)


@app.post("/save-graph")
async def save_graph_endpoint(request: Request, filename_base: str = Form(None), instruction: str = Form(None), graph_id: str = Form(None)):
    uid = request.session.get("user_id")
    if not uid:
        return JSONResponse({"success": False, "error": "Not logged in"}, status_code=401)
    
    # Save metadata only
    form = await request.form()
    nodes = form.get("nodes")
    edges = form.get("edges")
    
    # Generate filename_base if not provided
    if not filename_base:
        filename_base = f"pid_graph_{uuid.uuid4().hex[:8]}"
    
    # If graph_id is provided and not empty, update existing graph; otherwise create new
    try:
        if graph_id and graph_id.strip():
            try:
                gid = int(graph_id)
                auth.update_graph(gid, uid, filename_base, instruction or "", json_loads(nodes) if nodes else None, json_loads(edges) if edges else None)
                print(f"[Save] Updated graph id={gid} for user={uid}")
            except (ValueError, Exception) as e:
                print(f"[Save] Error updating graph: {e}")
                gid = auth.save_graph(uid, filename_base, instruction or "", json_loads(nodes) if nodes else None, json_loads(edges) if edges else None)
                print(f"[Save] Created new graph id={gid} for user={uid}")
        else:
            gid = auth.save_graph(uid, filename_base, instruction or "", json_loads(nodes) if nodes else None, json_loads(edges) if edges else None)
            print(f"[Save] Created new graph id={gid} for user={uid}")
        
        return JSONResponse({"success": True, "graph_id": gid})
    except Exception as e:
        print(f"[Save] Error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/chat")
async def chat(request: Request):
    """
    Handle chat messages and generate/update PI&D diagrams based on conversational input.
    """
    uid = request.session.get("user_id")
    if not uid:
        return json_response({"error": "Not authenticated"}, status_code=401)
    
    try:
        body = await request.json()
        user_message = body.get("message", "").strip()
        chat_history = body.get("history", [])
        
        if not user_message:
            return json_response({"error": "Empty message"}, status_code=400)
        
        # Reconstruct conversation context for the graph generator
        # Extract any previous instructions from chat history
        previous_instructions = ""
        if chat_history:
            for msg in chat_history:
                if msg.get("role") == "user":
                    previous_instructions += msg.get("content", "") + "\n"
        
        # Build the full instruction context
        full_instruction = previous_instructions + user_message if previous_instructions else user_message
        filename_base = f"pid_graph_{uuid.uuid4().hex}"
        
        # Generate or update the graph
        try:
            graph_data = generate_pid_graph(full_instruction, filename_base)
            
            # Debug: print the raw graph_data
            print(f"[Chat] Raw graph_data repr: {repr(graph_data)[:500]}")
            
            # Check if graph generation failed
            if graph_data.get("error"):
                error_msg = graph_data.get("error", "Unknown error")
                print(f"[Chat] Graph generation error: {error_msg}")
                return json_response({
                    "response": "I couldn't generate the P&ID diagram. Could you try describing your system differently?",
                    "error": error_msg,
                    "nodes": [],
                    "edges": []
                }, status_code=200)
        except Exception as e:
            error_msg = f"Failed to generate graph: {str(e)}"
            print(f"[Chat] Exception: {error_msg}")
            import traceback
            traceback.print_exc()
            return json_response({
                "response": "I couldn't generate the P&ID diagram. Could you try describing your system differently?",
                "error": error_msg
            }, status_code=500)
        
        # Prepare response with graph data
        default_text = "I've generated your P&ID diagram. You can customize the symbols using the Customize Symbols button, or continue describing your system to make changes."
        
        # Safely convert nodes and edges to JSON-serializable format
        try:
            # First, deep clean the graph data to remove any problematic objects
            print(f"[Chat] Starting to clean graph_data...")
            graph_data = deep_clean_for_json(graph_data)
            print(f"[Chat] Graph_data cleaned successfully")
            
            # Prefer assistant suggestions/questions when available
            assistant_msg = graph_data.get("assistant_message") or ""
            nodes_data = graph_data.get("nodes", [])
            
            if isinstance(nodes_data, set):
                nodes_list = list(nodes_data)
            else:
                nodes_list = list(nodes_data) if nodes_data else []
            
            # Filter out None and empty values
            nodes_list = [str(n) for n in nodes_list if n]
            
            # Convert edges from tuples to lists
            edges_data = graph_data.get("edges", [])
            
            edges_list = []
            for edge in edges_data:
                if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                    edges_list.append([str(edge[0]), str(edge[1])])
                elif isinstance(edge, dict) and "source" in edge and "target" in edge:
                    edges_list.append({
                        "source": str(edge.get("source", "")),
                        "target": str(edge.get("target", ""))
                    })
            
            response_data = {
                "response": (assistant_msg.strip() + ("\n\n" + default_text if default_text else "")).strip() if assistant_msg else default_text,
                "nodes": nodes_list,
                "edges": edges_list,
                "filename_base": filename_base,
                "instruction": full_instruction
            }
            
            # Final deep clean of response
            response_data = deep_clean_for_json(response_data)
            print(f"[Chat] Response data prepared successfully")
            
            # Verify all values are JSON-serializable
            json_str = json.dumps(response_data, cls=SafeJSONEncoder)
            print(f"[Chat] Response successfully serialized, length: {len(json_str)}")
            
        except Exception as e:
            print(f"[Chat] Error preparing response data: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return json_response({
                "response": "Generated diagram but encountered an error preparing the response. Please try again.",
                "error": str(e)
            }, status_code=500)
        
        # Return the response using safe JSON encoding
        try:
            return json_response(response_data)
        except Exception as e:
            print(f"[Chat] Final serialization error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            # Last resort - return a very simple response
            return json_response({
                "response": "Generated a diagram but encountered a serialization error",
                "error": str(e),
                "nodes": [],
                "edges": []
            }, status_code=500)
        
    except Exception as e:
        print(f"[Chat] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "error": str(e),
            "response": "An unexpected error occurred. Please try again."
        }, status_code=500)


def json_loads(s):
    import json
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


@app.get("/my-graphs")
async def my_graphs(request: Request):
    """View all saved graphs for the logged-in user."""
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse(url="/login", status_code=303)
    user = auth.get_user(uid)
    graphs = auth.get_graphs_for_user(uid)
    return templates.TemplateResponse("my_graphs.html", {"request": request, "user": user, "graphs": graphs})


@app.get("/load-graph/{graph_id}")
async def load_graph(request: Request, graph_id: int):
    """Load a saved graph for viewing/editing."""
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse(url="/login", status_code=303)
    
    # Get the graph and verify ownership
    graphs = auth.get_graphs_for_user(uid)
    graph = next((g for g in graphs if g["id"] == graph_id), None)
    
    if not graph:
        user = auth.get_user(uid)
        return templates.TemplateResponse("index.html", index_context(request, user=user, error="Graph not found or access denied"))
    
    user = auth.get_user(uid)
    return templates.TemplateResponse("index.html", index_context(
        request,
        user=user,
        instruction=graph["instruction"],
        nodes=graph["nodes"],
        edges=graph["edges"],
        filename_base=graph["filename"].replace(".png", "") if graph["filename"] else None,
        graph_id=graph["id"],
    ))


@app.get("/download-graph/{graph_id}")
async def download_graph(request: Request, graph_id: int):
    """Download a saved graph as JSON."""
    from fastapi.responses import JSONResponse
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse(url="/login", status_code=303)
    
    # Get the graph and verify ownership
    graphs = auth.get_graphs_for_user(uid)
    graph = next((g for g in graphs if g["id"] == graph_id), None)
    
    if not graph:
        return JSONResponse({"error": "Graph not found or access denied"}, status_code=404)
    
    # Prepare download data
    download_data = {
        "id": graph["id"],
        "instruction": graph["instruction"],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "created_at": graph["created_at"]
    }
    
    filename = f"pid_graph_{graph_id}.json"
    return JSONResponse(
        content=download_data,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/delete-graph/{graph_id}")
async def delete_graph(request: Request, graph_id: int):
    """Delete a saved graph."""
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse(url="/login", status_code=303)
    
    # Verify ownership before deleting
    graphs = auth.get_graphs_for_user(uid)
    graph = next((g for g in graphs if g["id"] == graph_id), None)
    
    if not graph:
        return RedirectResponse(url="/my-graphs", status_code=303)
    
    auth.delete_graph(graph_id)
    print(f"[Delete] Deleted graph id={graph_id} for user={uid}")
    return RedirectResponse(url="/my-graphs", status_code=303)


@app.post("/upload-graph")
async def upload_graph(request: Request):
    """Upload and validate a JSON graph file."""
    from fastapi.responses import JSONResponse
    uid = request.session.get("user_id")
    if not uid:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        body = await request.json()
        
        # Validate required fields
        if not isinstance(body, dict):
            return JSONResponse({"error": "Invalid JSON structure"}, status_code=400)
        
        instruction = body.get("instruction", "")
        nodes = body.get("nodes")
        edges = body.get("edges")
        
        # Validate data types and structure
        if not isinstance(instruction, str):
            return JSONResponse({"error": "Invalid instruction field"}, status_code=400)
        
        if nodes is not None and not isinstance(nodes, list):
            return JSONResponse({"error": "Invalid nodes field - must be array"}, status_code=400)
        
        if edges is not None and not isinstance(edges, list):
            return JSONResponse({"error": "Invalid edges field - must be array"}, status_code=400)
        
        # Validate node structure
        if nodes:
            if len(nodes) > 200:
                return JSONResponse({"error": "Too many nodes (max 200)"}, status_code=400)
            
            for node in nodes:
                if not isinstance(node, (str, dict)):
                    return JSONResponse({"error": "Invalid node format"}, status_code=400)
                if isinstance(node, dict) and "id" not in node:
                    return JSONResponse({"error": "Node missing id field"}, status_code=400)
        
        # Validate edge structure
        if edges:
            if len(edges) > 300:
                return JSONResponse({"error": "Too many edges (max 300)"}, status_code=400)
            
            for edge in edges:
                if not isinstance(edge, (list, dict)):
                    return JSONResponse({"error": "Invalid edge format"}, status_code=400)
        
        # Save the uploaded graph
        filename_base = f"pid_upload_{uuid.uuid4().hex}"
        graph_id = auth.save_graph(uid, filename_base, instruction, nodes, edges)
        
        print(f"[Upload] Uploaded graph id={graph_id} for user={uid}")
        return JSONResponse({"success": True, "graph_id": graph_id})
        
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON format"}, status_code=400)
    except Exception as e:
        print(f"[Upload] Error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/me")
async def me(request: Request):
    """Return current session user details (debug aid)."""
    uid = request.session.get("user_id")
    if not uid:
        return {"logged_in": False}
    user = auth.get_user(uid)
    return {"logged_in": True, "user": user}


@app.get("/api/graphs/{graph_id}/description")
async def get_graph_description_api(graph_id: int, request: Request):
    """Get the CURRENT description of a graph (not versioned)"""
    uid = request.session.get("user_id")
    if not uid:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    graphs = auth.get_graphs_for_user(uid)
    graph = next((g for g in graphs if g["id"] == graph_id), None)
    
    if not graph:
        return JSONResponse({"error": "Graph not found"}, status_code=404)
    
    return JSONResponse({
        "success": True,
        "description": graph["instruction"],
        "graph_id": graph_id
    })


@app.get("/api/graphs/{graph_id}/versions")
async def get_graph_versions_api(graph_id: int, request: Request):
    """Get all versions for a specific graph"""
    uid = request.session.get("user_id")
    if not uid:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    versions = auth.get_graph_versions(graph_id, uid)
    return JSONResponse({"success": True, "versions": versions})


@app.post("/api/graphs/{graph_id}/versions/{version_number}/restore")
async def restore_graph_version_api(graph_id: int, version_number: int, request: Request):
    """Restore a graph to a specific version"""
    uid = request.session.get("user_id")
    if not uid:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    success = auth.restore_graph_version(graph_id, version_number, uid)
    if success:
        return JSONResponse({"success": True, "message": f"Restored to version {version_number}"})
    else:
        return JSONResponse({"error": "Failed to restore version"}, status_code=404)


@app.patch("/api/graphs/{graph_id}/versions/{version_number}/description")
async def update_version_description_api(graph_id: int, version_number: int, request: Request):
    """Update the description of a specific version snapshot"""
    uid = request.session.get("user_id")
    if not uid:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        body = await request.json()
        description = body.get("description", "")
        
        success = auth.update_version_description(graph_id, version_number, uid, description)
        if success:
            return JSONResponse({"success": True})
        else:
            return JSONResponse({"error": "Version not found or access denied"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.patch("/api/graphs/{graph_id}/description")
async def update_graph_description(graph_id: int, request: Request):
    """Update the description/instruction of a graph"""
    uid = request.session.get("user_id")
    if not uid:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        body = await request.json()
        description = body.get("description", "")
        
        success = auth.update_graph_description(graph_id, uid, description)
        if success:
            return JSONResponse({"success": True})
        else:
            return JSONResponse({"error": "Graph not found or access denied"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/symbols")
async def get_symbols(request: Request):
    """Return list of all available P&ID symbols with metadata (user-specific custom symbols)."""
    symbols_dir = os.path.join(os.path.dirname(__file__), "..", "static", "symbols")
    custom_dir = os.path.join(symbols_dir, "custom")
    try:
        symbols_list = []
        
        # Get all PNG files in the main symbols directory
        symbol_files = sorted([f for f in os.listdir(symbols_dir) if f.endswith('.png')])
        for f in symbol_files:
            name = f.replace('.png', '').replace('_', ' ').title()
            symbols_list.append({
                "name": name,
                "category": "Standard",
                "path": f"/static/symbols/{f}"
            })
        
        # Get user-specific custom symbols if logged in
        user_id = request.session.get("user_id")
        if user_id and os.path.exists(custom_dir):
            user_custom_dir = os.path.join(custom_dir, str(user_id))
            if os.path.exists(user_custom_dir):
                custom_files = sorted([f for f in os.listdir(user_custom_dir) if f.endswith(('.png', '.jpg', '.jpeg', '.svg'))])
                for f in custom_files:
                    name = f.replace('.png', '').replace('.jpg', '').replace('.jpeg', '').replace('.svg', '').replace('_', ' ').title()
                    symbols_list.append({
                        "name": name,
                        "category": "Custom",
                        "path": f"/static/symbols/custom/{user_id}/{f}"
                    })
        
        return {
            "success": True,
            "count": len(symbols_list),
            "symbols": symbols_list
        }
    except Exception as e:
        print(f"[API] Error listing symbols: {e}")
        return {
            "success": False,
            "error": str(e),
            "symbols": []
        }


@app.post("/api/symbols/upload")
async def upload_custom_symbol(request: Request, file: UploadFile = File(...)):
    """Upload a custom symbol image (user-specific)."""
    try:
        # Check if user is logged in
        user_id = request.session.get("user_id")
        if not user_id:
            return JSONResponse(
                {"success": False, "error": "Must be logged in to upload custom symbols"},
                status_code=401
            )
        
        # Validate file type
        if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.svg')):
            return JSONResponse(
                {"success": False, "error": "Only PNG, JPG, JPEG, and SVG files are allowed"},
                status_code=400
            )
        
        # Create user-specific directory
        user_custom_dir = CUSTOM_SYMBOLS_DIR / str(user_id)
        user_custom_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate safe filename (preserve extension)
        file_ext = os.path.splitext(file.filename)[1]
        safe_name = f"{uuid.uuid4().hex}{file_ext}"
        file_path = user_custom_dir / safe_name
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Return the relative path that can be used in imageUrl
        relative_path = f"/static/symbols/custom/{user_id}/{safe_name}"
        
        return {
            "success": True,
            "path": relative_path,
            "filename": safe_name
        }
    except Exception as e:
        print(f"[API] Error uploading symbol: {e}")
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )