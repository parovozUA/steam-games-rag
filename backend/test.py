import httpx
import asyncio
import yaml

async def run():
    with open('eval/dataset.yaml', encoding='utf-8') as f:
        cases = yaml.safe_load(f)['cases']
    async with httpx.AsyncClient() as client:
        async with client.stream('POST', 'http://localhost:8000/api/v1/search', json={'query': cases[0]['query'], 'debug': True}, timeout=20) as r:
            with open('test_out.txt', 'w', encoding='utf-8') as f:
                async for line in r.aiter_lines():
                    f.write(line + '\n')
                    if line.startswith("event: summary_chunk"):
                        break

asyncio.run(run())
