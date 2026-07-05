    if weights.get("dependency", 0) > 0:
        recs.append({"title": "Fix high/critical dependency vulnerabilities", "weight": weights["dependency"], "source": "dependency"})