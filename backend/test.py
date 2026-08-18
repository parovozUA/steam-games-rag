import asyncio
from pathlib import Path

import httpx
import yaml


async def run() -> None:
    cases_content = await asyncio.to_thread(Path("eval/dataset.yaml").read_text, encoding="utf-8")
    cases = yaml.safe_load(cases_content)["cases"]
    async with httpx.AsyncClient(timeout=20) as client:
        async with client.stream(
            "POST",
            "http://localhost:8000/api/v1/search",
            json={"query": cases[0]["query"], "debug": True},
        ) as r:
            output_lines: list[str] = []
            async for line in r.aiter_lines():
                output_lines.append(line + "\n")
                if line.startswith("event: summary_chunk"):
                    break
            await asyncio.to_thread(
                Path("test_out.txt").write_text, "".join(output_lines), encoding="utf-8"
            )


if __name__ == "__main__":
    asyncio.run(run())
