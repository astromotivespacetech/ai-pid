import os
import json

try:
    import openai
except Exception:
    openai = None


def generate_pid_graph(instruction: str, filename_base: str = "pid_graph", existing_graph: dict = None):
    """Generate graph data by parsing `instruction` using OpenAI.

    This function uses the OpenAI API to parse the provided text into a JSON
    structure with `nodes` and `edges`. No local/fallback parsing is performed;
    if the LLM parsing fails for any reason, an error message is printed and
    returned in a dict with an `error` key.
    
    If existing_graph is provided, the LLM will modify the existing graph based on the instruction.
    """
    nodes = set()
    edges = []

    def clean_parsed_data(obj):
        """Recursively clean parsed JSON to remove undefined/null values."""
        if obj is None:
            return None
        if isinstance(obj, dict):
            return {k: clean_parsed_data(v) for k, v in obj.items() if v is not None and str(v) != "undefined"}
        if isinstance(obj, list):
            return [clean_parsed_data(item) for item in obj if item is not None and str(item) != "undefined"]
        if isinstance(obj, str) and obj.lower() == "undefined":
            return None
        return obj

    def parse_with_llm(text: str):
        """Use OpenAI to parse the instruction into nodes/edges JSON.

        Uses prompt caching for the system message to reduce API costs on subsequent calls.
        Caches are ephemeral (5 minute TTL), so the system prompt is reused across multiple
        requests from the same user within 5 minutes, reducing token costs by ~90% on cache hits.

        Returns the parsed dict on success, or None on failure.
        """
        if openai is None:
            print("[LLM ERROR] openai package not installed; cannot parse instruction")
            return None
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[LLM ERROR] OPENAI_API_KEY not set in environment; cannot parse instruction")
            return None

        openai.api_key = api_key
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        system = (
            "You are a PI&D (Piping & Instrumentation Diagram) parser. Convert engineering descriptions into JSON graph structures.\n\n"
            "SYNTAX RULES:\n"
            "- 'feeds', 'supplies', 'sends to', 'connects to', 'flows to', '->', '=>' all mean: creates an edge from A to B\n"
            "- 'then' or 'followed by' or commas between items = series connection (chain of edges)\n"
            "- 'and' = parallel connection (same source, multiple targets) OR just list multiple items\n"
            "- Equipment types: pump, valve (ball/check/gate/globe/control), heat exchanger, tank, vessel, compressor, filter, separator, column, turbine, etc.\n"
            "- Abbreviations: HX=heat exchanger, UV=ultraviolet, PSV=pressure safety valve, CV=control valve\n\n"
            "EXAMPLES:\n"
            "1. 'pump feeds heat exchanger then tank' -> nodes=[pump, heat exchanger, tank], edges=[[pump, HX], [HX, tank]]\n"
            "2. 'compressor feeds tank, then check valve, then solenoid valve' -> nodes=[compressor, tank, check valve, solenoid valve], edges=[[comp, tank], [tank, check], [check, solenoid]]\n"
            "3. 'pump supplies both HX and filter' -> nodes=[pump, heat exchanger, filter], edges=[[pump, HX], [pump, filter]]\n\n"
            "OUTPUT FORMAT:\n"
            "Return ONLY a JSON object with these keys:\n"
            "- nodes: list of strings (unique equipment names)\n"
            "- edges: list of [source, target] pairs\n"
            "- assistant: optional string with clarifying questions or suggestions\n"
            "No prose, no markdown, only JSON."
        )

        if existing_graph and (existing_graph.get("nodes") or existing_graph.get("edges")):
            user = (
                "You are modifying an existing PI&D diagram. Current diagram:\n"
                f"Nodes: {existing_graph.get('nodes', [])}\n"
                f"Edges: {existing_graph.get('edges', [])}\n\n"
                "Based on the following instruction, modify the diagram by adding, removing, or changing nodes and edges. "
                "Return ONLY a JSON object with keys: nodes (complete list), edges (complete list),"
                " and assistant (optional suggestions/questions string).\n\n"
                f"Instruction: {text.strip()}\n\nRespond with JSON only."
            )
        else:
            user = (
                "Parse the following description and return ONLY a JSON object with keys: nodes, edges,"
                " and assistant (optional suggestions/questions string)."
            )
            user += "\n\nDescription:\n" + text.strip() + "\n\nRespond with JSON only."

        try:
            client = None
            if hasattr(openai, "OpenAI"):
                client = openai.OpenAI()

            # Try ChatCompletion API with prompt caching
            if client is not None and hasattr(client, "chat"):
                # Use prompt caching for system message (reduces costs on subsequent calls)
                # Cache is stored server-side and reused if the same system+user combo is sent
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": system,
                            "cache_control": {"type": "ephemeral"}  # Ephemeral cache: 5 minute TTL
                        },
                        {
                            "role": "user",
                            "content": user
                        }
                    ],
                    temperature=0.0,
                    max_tokens=500,
                )
                content = resp.choices[0].message.content if resp.choices else None
            # Fallback to older API if needed
            elif hasattr(openai, "ChatCompletion"):
                resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0.0,
                    max_tokens=500,
                )
                # Extract text based on response format
                if hasattr(resp, "choices") and resp.choices:
                    content = resp.choices[0].message.content
                else:
                    content = resp.get("choices", [{}])[0].get("message", {}).get("content")
            else:
                raise RuntimeError("No compatible OpenAI client API available")

            # Extract text from response (already handled above for most cases)
            if not content:
                # Fallback: try extracting from response object
                try:
                    if hasattr(resp, "choices") and resp.choices:
                        c0 = resp.choices[0]
                        if hasattr(c0, "message"):
                            content = c0.message.content
                        elif hasattr(c0, "text"):
                            content = c0.text
                except Exception:
                    content = None

            if not content:
                        content = rdict.get("output_text") or None
                        if not content:
                            outs = rdict.get("output") or rdict.get("choices") or []
                            if outs:
                                first = outs[0]
                                if isinstance(first, dict):
                                    cont = first.get("content") or first.get("message")
                                    if isinstance(cont, list) and cont:
                                        content = cont[0].get("text") or cont[0].get("content")
                                    else:
                                        content = first.get("text")
                except Exception:
                    content = None

            # 5) last resort: string form of the response
            if not content:
                try:
                    content = str(resp)
                except Exception:
                    content = None

            if not content:
                # save raw response for debugging
                dbg_dir = "output"
                os.makedirs(dbg_dir, exist_ok=True)
                raw_path = os.path.join(dbg_dir, "last_llm_response.txt")
                try:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(repr(resp))
                except Exception:
                    pass
                raise RuntimeError("Could not extract text from OpenAI response; saved raw response for inspection")

            content = content.strip()

            # Try to extract JSON from the response. Use a JSONDecoder to
            # robustly parse the first JSON object and ignore trailing text.
            start = content.find("{")
            content_json = content[start:] if start != -1 else content
            try:
                parsed = json.loads(content_json)
                # Clean the parsed data to remove undefined values
                return clean_parsed_data(parsed)
            except json.JSONDecodeError:
                try:
                    decoder = json.JSONDecoder()
                    parsed, _ = decoder.raw_decode(content_json)
                    # Clean the parsed data to remove undefined values
                    return clean_parsed_data(parsed)
                except Exception as e:
                    dbg_dir = "output"
                    os.makedirs(dbg_dir, exist_ok=True)
                    raw_path = os.path.join(dbg_dir, "last_llm_response.txt")
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"[LLM ERROR] failed to parse JSON from LLM response: {e}. Saved raw to {raw_path}")
                    return None
        except Exception as e:
            print(f"[LLM ERROR] OpenAI parsing failed: {e}")
            return None

    parsed = parse_with_llm(instruction)
    if not parsed or not isinstance(parsed, dict):
        print("[LLM ERROR] LLM parsing failed or returned invalid output; no fallback parsing will be attempted")
        return {"error": "LLM parsing failed"}

    assistant_text = parsed.get("assistant") or parsed.get("notes") or parsed.get("questions")
    if isinstance(assistant_text, (list, dict)):
        try:
            assistant_text = json.dumps(assistant_text)
        except Exception:
            assistant_text = str(assistant_text)

    for n in parsed.get("nodes", []):
        nid = n.get("id") if isinstance(n, dict) else str(n)
        nodes.add(nid)
    for e in parsed.get("edges", []):
        if isinstance(e, list) and len(e) >= 2:
            src, tgt = e[0], e[1]
        elif isinstance(e, dict):
            # Accept common key names from different parsers
            src = e.get("source") or e.get("from") or e.get("src") or e.get("a")
            tgt = e.get("target") or e.get("to") or e.get("dst") or e.get("b")
        else:
            src = tgt = None

        if src and tgt:
            edges.append((src, tgt))

    # If parsing produced no nodes/edges, treat as an error
    if not nodes and not edges:
        print("[LLM ERROR] Parsing produced no nodes or edges")
        return {"error": "Parsing produced no nodes or edges"}

    # Visualization rendering removed; return parsed data only
    # Clean nodes and edges before returning
    clean_nodes = [str(n) for n in nodes if n is not None and str(n) != "undefined"]
    clean_edges = [(str(src), str(tgt)) for src, tgt in edges if src is not None and tgt is not None and str(src) != "undefined" and str(tgt) != "undefined"]
    
    return {"nodes": clean_nodes, "edges": clean_edges, "assistant_message": assistant_text or "", "graph_file": None}