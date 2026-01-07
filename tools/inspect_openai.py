from openai import OpenAI
import os
import sys
import json

def main():
    instruction = "A supplies B. B connects to C."
    if len(sys.argv) > 1:
        instruction = sys.argv[1]

    system = (
        "You are a parser that converts short engineering text descriptions into a compact JSON"
        " representation describing nodes and directed edges for a PI&D-like diagram."
    )

    user = (
        "Parse the following description and return ONLY a JSON object with two keys: nodes and edges."
    )
    user += "\n\nDescription:\n" + instruction.strip() + "\n\nRespond with JSON only."

    client = OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-5.2")

    try:
        resp = client.responses.create(model=model, input=user, temperature=0.0, max_output_tokens=1000)
    except TypeError:
        # Try without max_output_tokens if SDK variant rejects it
        resp = client.responses.create(model=model, input=user, temperature=0.0)

    # Print raw repr and try to serialize to JSON for inspection
    print("--- RESPONSE REPR ---")
    try:
        print(repr(resp))
    except Exception as e:
        print(f"repr(resp) failed: {e}")

    print("--- OUTPUT_TEXT (if present) ---")
    try:
        print(getattr(resp, "output_text", None))
    except Exception:
        print(None)

    print("--- to_dict (if present) ---")
    try:
        if hasattr(resp, "to_dict"):
            print(json.dumps(resp.to_dict(), indent=2))
        else:
            # fallback: try dict conversion
            print(json.dumps(dict(resp), indent=2))
    except Exception as e:
        print(f"to_dict/json dump failed: {e}")

    # Save raw for later
    outdir = "output"
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "inspect_raw_response.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(repr(resp))
    except Exception as e:
        print(f"Failed to save raw response: {e}")

    print(f"Saved raw response to {path}")

if __name__ == "__main__":
    main()
