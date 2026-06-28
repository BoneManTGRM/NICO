def render_html(payload):
    import html, json
    return '<html><body><pre>' + html.escape(json.dumps(payload, indent=2)) + '</pre></body></html>'
