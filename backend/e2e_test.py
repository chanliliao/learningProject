"""E2E test: upload XML, approve all gates, verify completion."""
import asyncio
import sys
import httpx

BASE = "http://localhost:8000/api"
XML_PATH = "app/schemas/acord_life_sample.xml"


async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        # 1. Health checks
        print("=== Health ===")
        r = await client.get(f"{BASE}/health")
        print(f"  /health: {r.status_code} {r.json()}")
        r = await client.get(f"{BASE}/health/db")
        print(f"  /health/db: {r.status_code} {r.json()}")
        r = await client.get(f"{BASE}/health/qdrant")
        print(f"  /health/qdrant: {r.status_code} {r.json()}")

        # 2. List schemas
        print("\n=== Schemas ===")
        r = await client.get(f"{BASE}/schemas")
        schemas = r.json()
        print(f"  schemas: {[s['name'] for s in schemas]}")
        if not schemas:
            print("ERROR: no schemas, run seed first")
            sys.exit(1)
        schema_id = schemas[0]["id"]

        # 3. Start run
        print(f"\n=== Start Run (schema_id={schema_id}) ===")
        with open(XML_PATH, "rb") as f:
            xml_bytes = f.read()
        r = await client.post(
            f"{BASE}/runs",
            files={"file": ("acord_life_sample.xml", xml_bytes, "text/xml")},
            data={"target_schema_id": str(schema_id)},
        )
        print(f"  POST /runs: {r.status_code}")
        if r.status_code != 201:
            print(f"  ERROR: {r.text}")
            sys.exit(1)
        run_data = r.json()
        run_id = run_data["run_id"]
        print(f"  run_id={run_id}, status={run_data['status']}")

        # 4. Check run state — should be awaiting_review at extract gate
        print(f"\n=== Run Detail (run_id={run_id}) ===")
        r = await client.get(f"{BASE}/runs/{run_id}")
        detail = r.json()
        run = detail["run"]
        stages = detail["stage_results"]
        mappings = detail["mappings"]
        audit = detail["audit"]
        print(f"  run.status={run['status']}")
        for s in stages:
            print(f"  stage: {s['stage']} → {s['status']}")
        print(f"  mappings count: {len(mappings)}")
        print(f"  audit events: {len(audit)}")

        # 5. Approve gates one by one
        gate_order = ["extract", "interpret", "map", "test"]
        for gate in gate_order:
            # Find this stage in current detail
            r = await client.get(f"{BASE}/runs/{run_id}")
            detail = r.json()
            run = detail["run"]
            stages_now = {s["stage"]: s["status"] for s in detail["stage_results"]}
            print(f"\n=== Gate: {gate} | run.status={run['status']} stages={stages_now} ===")
            if run["status"] in ("completed", "failed"):
                print(f"  Run already {run['status']}, stopping gate loop")
                break
            # Approve this stage
            r = await client.post(f"{BASE}/runs/{run_id}/stages/{gate}/approve")
            print(f"  POST /stages/{gate}/approve: {r.status_code} {r.json()}")
            if r.status_code not in (200, 201):
                print(f"  WARN: approve returned {r.status_code}: {r.text}")

        # 6. Final state
        print("\n=== Final State ===")
        r = await client.get(f"{BASE}/runs/{run_id}")
        detail = r.json()
        run = detail["run"]
        stages = detail["stage_results"]
        mappings = detail["mappings"]
        audit = detail["audit"]
        print(f"  run.status={run['status']}")
        for s in stages:
            print(f"  stage: {s['stage']} → {s['status']}")
        print(f"  approved mappings: {sum(1 for m in mappings if m['status'] == 'approved')}")
        print(f"  total audit events: {len(audit)}")
        for a in audit:
            print(f"    [{a['actor']}] {a['action']}")

        # 7. Test standalone audit route
        print("\n=== Standalone /audit endpoint ===")
        r = await client.get(f"{BASE}/runs/{run_id}/audit")
        print(f"  GET /runs/{run_id}/audit: {r.status_code}, events={len(r.json())}")

        # 8. Support chat
        print("\n=== Support Chat ===")
        r = await client.post(f"{BASE}/runs/{run_id}/support", json={"question": "What fields were mapped?"})
        print(f"  POST /support: {r.status_code}")
        if r.status_code == 200:
            resp = r.json()
            print(f"  answer (first 120 chars): {resp['answer'][:120]}")

        final = "PASS" if run["status"] == "completed" else f"FAIL (status={run['status']})"
        print(f"\n=== E2E Result: {final} ===")

asyncio.run(main())
