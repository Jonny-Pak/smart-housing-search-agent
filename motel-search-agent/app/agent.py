# app/agent.py
import json
import urllib.request
import urllib.parse
import os
from pathlib import Path
from typing import Any

# Load .env file from the project root (one level up from app/)
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

from google.adk.events import Event
from google.adk.workflow import DEFAULT_ROUTE, Workflow, node, START
from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor


def normalize_property_type(pt: str) -> str:
    """Helper to normalize property type values to standard 'phong_tro' or 'nha_nguyen_can'."""
    if not pt:
        return None
    pt_lower = str(pt).lower().strip()
    if 'house' in pt_lower or 'nhà' in pt_lower or 'nha' in pt_lower or 'nguyen_can' in pt_lower:
        return 'nha_nguyen_can'
    if 'room' in pt_lower or 'phòng' in pt_lower or 'phong' in pt_lower or 'trọ' in pt_lower or 'tro' in pt_lower:
        return 'phong_tro'
    return pt


def query_database(price_max: int = 5000000, property_type: str = None, user_lat: float = None, user_lng: float = None) -> list[dict]:
    """Queries the PostgreSQL room database based on maximum price, optional property_type, and optional user location (user_lat, user_lng)."""
    try:
        # 1. Establish connection to PostgreSQL using environment variables
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "123456"),
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=os.getenv("DB_PORT", "5432")
        )

        # Use RealDictCursor so results are returned as dictionaries instead of tuples
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        conditions = ["price <= %s", "is_active = TRUE", "expires_at > NOW()"]
        params = [price_max]
        pt = normalize_property_type(property_type)
        if pt:
            conditions.append("property_type = %s")
            params.append(pt)
        where_clause = " AND ".join(conditions)

        # 2. Execute SQL query (using parameter binding to prevent SQL injection)
        if user_lat is not None and user_lng is not None:
            query = f"""
                SELECT
                    id,
                    address AS title,
                    price,
                    address,
                    COALESCE(phone, 'Đang cập nhật') AS phone,
                    COALESCE(property_type, 'phong_tro') AS property_type,
                    ST_DistanceSphere(geom::geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geometry) AS distance_meters
                FROM motel_rooms
                WHERE {where_clause}
                ORDER BY distance_meters ASC
                LIMIT 5;
            """
            cursor.execute(query, (user_lng, user_lat, *params))
        else:
            query = f"""
                SELECT
                    id,
                    address AS title,
                    price,
                    address,
                    COALESCE(phone, 'Đang cập nhật') AS phone,
                    COALESCE(property_type, 'phong_tro') AS property_type
                FROM motel_rooms
                WHERE {where_clause}
                ORDER BY price ASC
                LIMIT 5;
            """
            cursor.execute(query, tuple(params))

        # 3. Fetch results
        raw_results = cursor.fetchall()

        # 4. Close connection
        cursor.close()
        conn.close()

        # Convert RealDictRow to standard list of dicts for JSON serialization
        formatted_results = []
        for row in raw_results:
            row_dict = dict(row)
            if 'price' in row_dict and row_dict['price'] is not None:
                row_dict['price'] = float(row_dict['price'])
            if 'distance_meters' in row_dict and row_dict['distance_meters'] is not None:
                row_dict['distance_meters'] = round(float(row_dict['distance_meters']))
            formatted_results.append(row_dict)
        return formatted_results

    except Exception as e:
        print(f"[DB ERROR] Failed to query PostgreSQL: {e}")
        # Return empty list on DB error so the agent can report no results found
        return []


def spatial_radius_search(lat: float, lng: float, radius_meters: int = 500000, property_type: str = None) -> list[dict]:
    """Queries the PostgreSQL database for rooms within a specific radius using PostGIS and optional property_type ('phong_tro' or 'nha_nguyen_can')."""
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "123456"),
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=os.getenv("DB_PORT", "5432")
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        conditions = [
            "is_active = TRUE",
            "expires_at > NOW()"
        ]
        params = []
        pt = normalize_property_type(property_type)
        if pt:
            conditions.append("property_type = %s")
            params.append(pt)
        where_clause = " AND ".join(conditions)

        # PostGIS note: coordinates must always be in (Longitude, Latitude) -> (lng, lat) order
        query = f"""
            SELECT
                id,
                address AS title,
                price,
                address,
                COALESCE(phone, 'Đang cập nhật') AS phone,
                COALESCE(property_type, 'phong_tro') AS property_type,
                ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) AS distance_meters
            FROM motel_rooms
            WHERE {where_clause}
            ORDER BY distance_meters ASC
            LIMIT 5;
        """

        # Parameters: first 2 for ST_Distance, rest for ST_DWithin and conditions
        cursor.execute(query, (lng, lat, *params))

        raw_results = cursor.fetchall()
        cursor.close()
        conn.close()

        formatted_results = []
        for row in raw_results:
            row_dict = dict(row)
            # Cast Decimal to float for price
            if 'price' in row_dict and row_dict['price'] is not None:
                row_dict['price'] = float(row_dict['price'])

            # Cast and round distance in meters
            if 'distance_meters' in row_dict and row_dict['distance_meters'] is not None:
                row_dict['distance_meters'] = round(float(row_dict['distance_meters']))

            # Append center coordinates so the frontend can render the map
            row_dict['lat'] = lat
            row_dict['lng'] = lng

            formatted_results.append(row_dict)

        return formatted_results

    except Exception as e:
        print(f"[DB ERROR - SPATIAL] Failed to query PostgreSQL: {e}")
        return []


def add_new_room(address: str, price: int, phone: str, property_type: str = 'phong_tro') -> list[dict]:
    """Inserts a new room/house listing into the PostgreSQL motel_rooms table after geocoding the address via Nominatim API."""
    try:
        # 0. Validate required fields and Vietnamese phone number (must be exactly 10 digits)
        cleaned_phone = "".join(filter(str.isdigit, str(phone)))
        if not address or not address.strip():
            return [{"error": "Vui lòng cung cấp địa chỉ đầy đủ của bất động sản đang muốn cho thuê."}]
        if not price or int(price) <= 0:
            return [{"error": "Vui lòng cung cấp giá thuê hợp lệ theo tháng."}]
        if len(cleaned_phone) != 10 or not cleaned_phone.startswith("0"):
            return [{"error": "Số điện thoại liên hệ không hợp lệ. Vui lòng nhập số điện thoại tại Việt Nam gồm đúng 10 chữ số (bắt đầu bằng số 0)."}]

        pt = normalize_property_type(property_type) or 'phong_tro'

        # 1. Geocode address via OpenStreetMap Nominatim API
        search_query = address if ("Ho Chi Minh" in address or "Vietnam" in address) else f"{address}, Ho Chi Minh, Vietnam"
        query_str = urllib.parse.quote(search_query)
        url = f"https://nominatim.openstreetmap.org/search?q={query_str}&format=json&limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'SmartHousingSearch-AI/1.0'})

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        if not data:
            return [{"error": "Could not locate this address on the map. Please provide more detail (e.g., street name, district)."}]

        lat = float(data[0]['lat'])
        lng = float(data[0]['lon'])

        # 2. Connect to PostgreSQL and insert into PostGIS
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "123456"),
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=os.getenv("DB_PORT", "5432")
        )
        cursor = conn.cursor()
        query = """
            INSERT INTO motel_rooms (address, price, phone, property_type, expires_at, is_active, geom)
            VALUES (%s, %s, %s, %s, NOW() + INTERVAL '7 days', TRUE, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            RETURNING id;
        """
        cursor.execute(query, (address, price, phone, pt, lng, lat))
        inserted_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        return [{
            "id": inserted_id,
            "title": "Đăng tin thành công (Hiệu lực 7 ngày)!",
            "price": price,
            "address": address,
            "phone": phone,
            "property_type": pt,
            "lat": lat,
            "lng": lng,
            "message": f"Bất động sản tại '{address}' đã được định vị ({lat:.4f}, {lng:.4f}) và thêm vào hệ thống (hết hạn sau 7 ngày)."
        }]
    except Exception as e:
        print(f"[DB ERROR - INSERT] Failed to insert room: {e}")
        return [{"error": str(e), "message": "Listing failed due to a system error or the address could not be geolocated."}]


def calculate_affordability(monthly_income: float) -> dict:
    """
    Tư vấn ngân sách thuê nhà dựa trên thu nhập hàng tháng.
    Quy tắc: Ngân sách thuê nhà tối ưu nên nằm trong khoảng 25% - 35% thu nhập.
    Calculates optimal rental budget based on monthly income (optimal range: 25% - 35% of income).
    """
    try:
        income = float(monthly_income)
        min_budget = income * 0.25
        max_budget = income * 0.35
        return {
            "monthly_income": income,
            "min": min_budget,
            "max": max_budget,
            "advice": f"Với thu nhập {income:,.0f} VND/tháng, bạn nên chọn phòng trọ trong khoảng {min_budget:,.0f} - {max_budget:,.0f} VND để cân đối chi tiêu.",
            "advice_vi": f"Với thu nhập {income:,.0f} VND/tháng, bạn nên chọn phòng trọ trong khoảng {min_budget:,.0f} - {max_budget:,.0f} VND để cân đối chi tiêu.",
            "advice_en": f"With a monthly income of {income:,.0f} VND, your optimal rental budget is between {min_budget:,.0f} and {max_budget:,.0f} VND to balance your expenses."
        }
    except Exception as e:
        return {"error": "Vui lòng cung cấp thu nhập hàng tháng hợp lệ."}




# ---------------------------------------------------------------------------
# 1. Output schema for the classifier agent
# ---------------------------------------------------------------------------
class QueryCategory(BaseModel):
    """Classification output: 'spatial', 'simple', or 'insert'."""

    category: str = Field(
        description=(
            "Query type: 'spatial' for location-based/radius searches, "
            "'simple' for price/amenity-based filters or follow-up room searches, "
            "'insert' when the user wants to post, list, add, or rent out a new room/property OR when the user asks for affordability/budget consultation based on monthly salary/income."
        )
    )
    user_query: str = Field(
        description="The exact original user query string."
    )


# ---------------------------------------------------------------------------
# 2. Nodes
# ---------------------------------------------------------------------------
@node
def parse_query(ctx: Any, node_input: str) -> dict:
    """Parses raw user input and initializes the workflow state."""
    ctx.session.state["user_query"] = node_input
    return {"user_query": node_input}


@node
def classify_and_route(ctx: Any, node_input: Any) -> Event:
    """
    Reads the classifier's structured output and emits a routing signal.
    """
    category = "simple"  # safe default
    if isinstance(node_input, dict):
        category = node_input.get("category", "simple")
    elif hasattr(node_input, "category"):
        category = node_input.category

    user_query = ctx.session.state.get("user_query", "")
    # Emit route value so the graph can branch correctly
    if category == "insert":
        route_value = "insert"
    elif category == "spatial":
        route_value = "spatial"
    else:
        route_value = "simple"
    return Event(route=route_value, output=user_query)


# ---------------------------------------------------------------------------
# 3. LLM Agents
# ---------------------------------------------------------------------------
categorizer = LlmAgent(
    name="query_classifier",
    model="gemini-3.1-flash-lite-preview",
    output_schema=QueryCategory,
    instruction=(
        "Analyze the user request and classify it. "
        "Return 'insert' if the user expresses intent to post, add, list, or rent out a new room/property "
        "(e.g., 'I have a vacant room at...', 'Room for rent at...', 'Post a listing...', "
        "'Tôi có phòng trọ trống...', 'Cho thuê phòng...', 'Đăng tin...') OR if the user asks for budget/salary/affordability consultation "
        "('thu nhập', 'lương', 'salary', 'income', 'tư vấn ngân sách', 'khả năng chi trả', 'affordability', 'lương tôi...'). "
        "Return 'spatial' if the user mentions searching near locations, specific coordinates, proximity, or radius. "
        "Return 'simple' if the user asks for searching by price ranges, specific room amenities, or searching rooms matching a previously discussed budget. "
        "Also extract and copy the exact user request string into 'user_query'. "
        "CRITICAL LANGUAGE RULE: You must automatically detect the language of the user's query (English or Vietnamese). "
        "You MUST strictly respond, think, and format all output text and JSON data "
        "in that EXACT SAME language. Never mix languages."
    ),
)


simple_search_agent = LlmAgent(
    name="simple_search_agent",
    model="gemini-3.1-flash-lite-preview",
    tools=[query_database, calculate_affordability],
    instruction=(
        "You are a helpful rental assistant.\n"
        "Luôn ưu tiên lọc theo property_type nếu người dùng đề cập (ví dụ: 'nhà nguyên căn' hoặc 'phòng trọ'). "
        "Khi người dùng yêu cầu tìm kiếm, hãy kiểm tra xem họ muốn tìm 'phòng trọ' ('phong_tro'/room) hay 'nhà nguyên căn' ('nha_nguyen_can'/house). "
        "Nếu người dùng không chỉ định, hãy để property_type là None (trả về tất cả). "
        "Nếu người dùng chỉ định cụ thể, MUST truyền tham số property_type ('phong_tro' hoặc 'nha_nguyen_can') vào hàm tìm kiếm tương ứng.\n"
        "KỸ NĂNG TƯ VẤN & TÌM PHÒNG THEO NGÂN SÁCH (AFFORDABILITY & BUDGET SEARCH):\n"
        "1. Nếu người dùng hỏi tư vấn ngân sách từ thu nhập/lương, BẮT BUỘC gọi tool 'calculate_affordability' với tham số 'monthly_income' (chuyển đổi số tiền thu nhập sang số nguyên VND). Sau khi nhận kết quả từ tool, trả về một JSON array bắt đầu bằng [ và kết thúc bằng ] chứa đúng 1 object có 'ui_type': 'A2UI_BudgetAdvice' và 'data' (đảm bảo 'data' chứa 'monthly_income', 'min', 'max', 'advice', 'advice_vi', 'advice_en').\n"
        "2. Nếu người dùng yêu cầu 'Tìm phòng phù hợp với ngân sách đó', 'phù hợp với mức tư vấn trên', hoặc tìm phòng theo thu nhập đã bàn, hãy xác định mức ngân sách tối đa (max budget) từ câu tư vấn trước (hoặc gọi calculate_affordability nếu cần thiết) và truyền mức giá đó vào tham số 'price_max' khi gọi hàm 'query_database'.\n"
        "3. Extract the maximum price from the user's query (e.g., '3 million VND' or '3 triệu' means 3000000).\n"
        "4. If user location payload coordinates (lat, lng) are provided in the prompt, you MUST pass them to 'user_lat' and 'user_lng'. "
        "You MUST call 'query_database' passing 'price_max', 'property_type', 'user_lat', and 'user_lng'.\n"
        "5. For each room result, wrap it in a JSON object with 'ui_type': 'A2UI_Card' and 'data' "
        "   (ensure 'data' strictly includes 'id', 'title', 'price', 'address', 'phone', and 'distance_meters' if available).\n"
        "6. Return the final output as a raw JSON array starting with [ and ending with ]. Do NOT wrap in markdown code blocks. "
        "If the database returns 0 results, DO NOT return an empty array [] or any brackets. Simply output a helpful natural language explanation.\n"
        "CRITICAL LANGUAGE RULE: You must automatically detect the language of the user's query (English or Vietnamese). "
        "Hãy phản hồi lại cho người dùng theo ngôn ngữ họ đã chọn (EN/VI) xác nhận bạn đang tìm loại bất động sản tương ứng. "
        "You MUST strictly respond, think, and format all output text and JSON data "
        "(including card titles, descriptions, status notifications, and error messages) in that EXACT SAME language. "
        "If the user asks in English, translate the retrieved database data and return English text before wrapping it in the JSON schema. "
        "Never mix languages."
    )
)

spatial_search_agent = LlmAgent(
    name="spatial_search_agent",
    model="gemini-3.1-flash-lite-preview",
    tools=[spatial_radius_search],
    instruction=(
        "You are a location-based rental assistant.\n"
        "Luôn ưu tiên lọc theo property_type nếu người dùng đề cập (ví dụ: 'nhà nguyên căn' hoặc 'phòng trọ'). "
        "Khi người dùng yêu cầu tìm kiếm, hãy kiểm tra xem họ muốn tìm 'phòng trọ' ('phong_tro'/room) hay 'nhà nguyên căn' ('nha_nguyen_can'/house). "
        "Nếu người dùng không chỉ định, hãy để property_type là None (trả về tất cả). "
        "Nếu người dùng chỉ định cụ thể, MUST truyền tham số property_type ('phong_tro' hoặc 'nha_nguyen_can') vào hàm tìm kiếm tương ứng.\n"
        "1. Read the user's query carefully to identify any location name or coordinates and radius.\n"
        "2. If the user provides latitude and longitude numbers directly in the prompt, you MUST use them exactly as given.\n"
        "3. If the user provides a location name, estimate its latitude and longitude. "
        "   For landmarks in Ho Chi Minh City, use accurate coordinates: "
        "   'HCMC University of Natural Resources and Environment' (HCMUNRE / DH TNMT / ĐH Tài nguyên Môi trường) is at lat 10.8205, lng 106.6880; "
        "   'HCMC University of Industry' (HCMUI / IUH / ĐH Công nghiệp / Nguyen Van Bao) is at lat 10.8198, lng 106.6876. "
        "   You MUST NOT ask the user for coordinates if they provided a location name.\n"
        "4. Never report that no rooms were found within a radius. The search tool automatically returns the nearest available active rooms sorted by distance. Always present these nearest rooms to the user.\n"
        "5. Khi nhận được tọa độ người dùng trong payload (hoặc trong chuỗi 'Vị trí người dùng / User Location payload: lat=..., lng=...'), hãy sử dụng tọa độ đó để gọi hàm query (spatial_radius_search). Kết quả trả về phải bao gồm trường distance_meters. Hãy hiển thị thông tin này trong thẻ phòng trọ theo đơn vị mét hoặc km (ví dụ: 'Cách bạn 1.5km').\n"
        "6. Return the final output as a raw JSON array starting with [ and ending with ]. "
        "   Wrap each result in a JSON object with 'ui_type': 'A2UI_MapCard' and 'data' "
        "   (ensure 'data' strictly includes 'id', 'title', 'price', 'address', 'lat', 'lng', and 'distance_meters'). "
        "   Do NOT wrap the array in markdown code blocks like ```json. "
        "   If the database returns 0 results, DO NOT return an empty array [] or any brackets. Simply output a helpful natural language explanation.\n"
        "CRITICAL LANGUAGE RULE: You must automatically detect the language of the user's query (English or Vietnamese). "
        "Hãy phản hồi lại cho người dùng theo ngôn ngữ họ đã chọn (EN/VI) xác nhận bạn đang tìm loại bất động sản tương ứng. "
        "You MUST strictly respond, think, and format all output text and JSON data "
        "(including card titles, descriptions, status notifications, and error messages) in that EXACT SAME language. "
        "If the user asks in English, translate the retrieved database data and return English text before wrapping it in the JSON schema. "
        "Never mix languages."
    )
)

listing_agent = LlmAgent(
    name="listing_agent",
    model="gemini-3.1-flash-lite-preview",
    tools=[add_new_room, calculate_affordability],
    instruction=(
        "You are a rental listing and affordability advisory assistant.\n\n"
        "KỸ NĂNG TƯ VẤN (AFFORDABILITY ADVISORY SKILL): Nếu người dùng đề cập đến 'thu nhập', 'lương', 'salary', 'income', hoặc hỏi về khả năng chi trả / tư vấn ngân sách, bạn BẮT BUỘC phải gọi tool 'calculate_affordability' với tham số 'monthly_income' (chuyển đổi số tiền thu nhập sang số nguyên VND, ví dụ '10 triệu' là 10000000). "
        "Sau khi nhận kết quả từ tool calculate_affordability, hãy đưa ra lời khuyên chân thành và chủ động gợi ý tìm kiếm phòng trọ nằm trong khoảng ngân sách đó. "
        "Đồng thời, MUST trả về kết quả dưới dạng JSON array bắt đầu bằng [ và kết thúc bằng ] chứa một object với 'ui_type': 'A2UI_BudgetAdvice' và 'data' (đảm bảo 'data' chứa đầy đủ 'monthly_income', 'min', 'max', 'advice', 'advice_vi', 'advice_en'). Do NOT wrap in markdown code blocks.\n\n"
        "REQUIRED FIELDS CHECK FOR POSTING LISTINGS: When the user wants to list/post a room or house for rent, you MUST ensure they provide ALL 3 of the following details:\n"
        "1. Full address of the property ('address')\n"
        "2. Monthly rental price ('price', convert to integer)\n"
        "3. Contact phone number ('phone')\n"
        "Luôn ưu tiên lọc và phân loại theo property_type nếu người dùng đề cập ('nha_nguyen_can' hoặc 'phong_tro'). Khi đăng tin, mặc định là 'phong_tro' nếu không nói gì khác.\n\n"
        "PHONE NUMBER VALIDATION: Check that the contact phone number contains exactly 10 digits (Standard phone number in Vietnam starting with 0).\n\n"
        "IF ANY OF THE 3 REQUIRED FIELDS ARE MISSING OR IF THE PHONE NUMBER IS NOT EXACTLY 10 DIGITS:\n"
        "DO NOT call 'add_new_room'. DO NOT return any JSON array or brackets []. Simply respond in natural language politely explaining what information is missing or incorrect (e.g. asking the user to provide a valid 10-digit Vietnamese phone number, full address, or rent price).\n\n"
        "IF ALL REQUIRED FIELDS ARE PROVIDED AND VALID:\n"
        "ADDRESS NORMALIZATION: Format the raw address into a fully qualified official address in Vietnam (e.g. '45 Nguyễn Văn Bảo, Phường 4, Quận Gò Vấp, TP. HCM').\n"
        "DO NOT estimate coordinates yourself.\n"
        "MUST call the 'add_new_room' tool passing the normalized 'address', extracted integer 'price', 'phone', and 'property_type'.\n"
        "Wrap the tool's result in a JSON object with 'ui_type': 'A2UI_Card' and 'data'. "
        "Return a JSON array starting with [ and ending with ] containing this wrapped UI card. Do NOT wrap in markdown code blocks.\n\n"
        "CRITICAL LANGUAGE RULE: You must automatically detect the language of the user's query (English or Vietnamese). "
        "You MUST strictly respond, think, and format all output text and JSON data "
        "(including card titles, descriptions, status notifications, and error messages) in that EXACT SAME language. "
        "Never mix languages."
    )
)

# ---------------------------------------------------------------------------
# 4. Workflow — tuple-chain syntax with RoutingMap for conditional branching
# ---------------------------------------------------------------------------
root_workflow = Workflow(
    name="motel_search_workflow",
    timeout=120,
    edges=[
        (START, parse_query, categorizer, classify_and_route,
         {
             "insert": listing_agent,
             "spatial": spatial_search_agent,
             "simple": simple_search_agent,
         }),
    ],
)

root_agent = root_workflow
app = root_workflow