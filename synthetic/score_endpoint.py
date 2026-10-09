"""Send rows {id, establishment_type, full_details} to a Vertex AI endpoint and save its answers.

    python synthetic/score_endpoint.py <endpoint predict url> rows.json predictions.json
"""
import json, subprocess, sys, urllib.request

URL, rows_path, out_path = sys.argv[1:4]
rows = json.load(open(rows_path))
token = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()
out = []
for start in range(0, len(rows), 16):
    chunk = rows[start:start + 16]
    body = {"instances": [{"establishment_type": r["establishment_type"], "observation_summary": "", "full_details": r["full_details"]} for r in chunk]}
    request = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        answer = json.load(response)
    for row, prediction in zip(chunk, answer["predictions"]):
        out.append({"id": row["id"], **prediction})
    print(f"scored {len(out)}/{len(rows)}", flush=True)
json.dump(out, open(out_path, "w"), indent=1)
