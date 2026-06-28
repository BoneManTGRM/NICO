def render_json(payload):
    import json
    return json.dumps(payload, indent=2, sort_keys=True)
