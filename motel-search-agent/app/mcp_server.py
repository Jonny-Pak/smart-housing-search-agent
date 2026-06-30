import json
import os

import psycopg2

# pyrefly: ignore [missing-import]
from mcp.server import Server

# pyrefly: ignore [missing-import]
from mcp.server.stdio import stdio_server

# pyrefly: ignore [missing-import]
from mcp.types import TextContent, Tool
from psycopg2.extras import RealDictCursor

# Khởi tạo server
server = Server("motel-search-mcp")

# Lấy cấu hình DB từ biến môi trường (Bảo mật)
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql://Jonny-Pak:190705@localhost:5432/motel_db"
)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="spatial_radius_search",
            description="Tìm phòng trọ trong bán kính (mét) quanh tọa độ (lat, lng).",
            inputSchema={
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lng": {"type": "number"},
                    "radius_meters": {"type": "integer"},
                },
                "required": ["lat", "lng", "radius_meters"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "spatial_radius_search":
        lat = arguments["lat"]
        lng = arguments["lng"]
        radius = arguments["radius_meters"]

        try:
            conn = psycopg2.connect(DB_URL)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Sử dụng PostGIS ST_DWithin cho hiệu suất cao
            query = """
            SELECT id, address, price,
                   ST_Distance(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) as distance_meters
            FROM motel_rooms
            WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
            ORDER BY distance_meters ASC;
            """
            cur.execute(query, (lng, lat, lng, lat, radius))
            results = cur.fetchall()

            cur.close()
            conn.close()

            return [TextContent(type="text", text=json.dumps(results))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return [TextContent(type="text", text="Error: Tool not found")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
