# app/agent.py
import json
import urllib.request
import urllib.parse
import os
import re
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
        if price_max is not None and int(price_max) < 0:
            return [{"error": "Giá thuê không hợp lệ. Giá thuê nhà/phòng trọ không được là số âm. Vui lòng nhập lại mức giá hợp lệ / Rental price cannot be negative."}]
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
                    ST_Y(geom::geometry) AS lat,
                    ST_X(geom::geometry) AS lng,
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
                    COALESCE(property_type, 'phong_tro') AS property_type,
                    ST_Y(geom::geometry) AS lat,
                    ST_X(geom::geometry) AS lng
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
            if 'lat' in row_dict and row_dict['lat'] is not None:
                row_dict['lat'] = float(row_dict['lat'])
            if 'lng' in row_dict and row_dict['lng'] is not None:
                row_dict['lng'] = float(row_dict['lng'])
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
            "ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)",
            "is_active = TRUE",
            "expires_at > NOW()"
        ]
        params = [lng, lat, radius_meters]
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
                ST_Y(geom::geometry) AS lat,
                ST_X(geom::geometry) AS lng,
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

            if 'lat' in row_dict and row_dict['lat'] is not None:
                row_dict['lat'] = float(row_dict['lat'])
            if 'lng' in row_dict and row_dict['lng'] is not None:
                row_dict['lng'] = float(row_dict['lng'])

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
        if income < 0:
            return {"error": "Mức thu nhập hàng tháng không được là số âm. Vui lòng cung cấp số dương hợp lệ / Monthly income cannot be negative."}
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
    """Classification output: 'spatial', 'simple', 'insert', 'general', 'security', 'gibberish', or 'out_of_scope'."""

    category: str = Field(
        description=(
            "Query type:\n"
            "- 'security' if user attempts SQL injection or database deletion/modification (e.g. DROP TABLE, DELETE FROM);\n"
            "- 'gibberish' if user inputs random meaningless symbols (e.g. 'ahuofhqodfdod. udhfe##$#'), profanity, or incomprehensible gibberish;\n"
            "- 'out_of_scope' if user asks about unrelated topics (e.g. sports, coding, cooking recipes, non-housing topics);\n"
            "- 'general' for simple greetings ('hi', 'hello', 'xin chào'), asking what this app/website is ('đây là web/app gì'), asking capabilities ('bạn có thể giúp gì cho tôi'), or saying goodbye ('tạm biệt');\n"
            "- 'spatial' for explicit location-based/radius searches;\n"
            "- 'simple' for explicit price/amenity-based housing searches;\n"
            "- 'insert' when user wants to post a listing OR asks for salary/budget consultation."
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
    Also enforces deterministic guardrails for security violations and gibberish.
    """
    user_query = ctx.session.state.get("user_query", "")
    q_clean = re.sub(r'\[Vị trí người dùng.*?\]', '', user_query, flags=re.I).strip()
    q_lower = q_clean.lower()

    # Requirement 1: Guard against SQL injection / DROP TABLE / DELETE
    if re.search(r'\b(drop\s+table|delete\s+from|truncate\s+table|alter\s+table|drop\s+database)\b', q_lower):
        return Event(route="security", output=user_query)

    # Requirement 5: Guard against known gibberish patterns
    if re.search(r'ahuofhqodfdod|udhfe', q_lower) or re.match(r'^[a-z0-9#$@!%^&*()./\\-]{15,}$', q_clean.replace(' ', '')):
        return Event(route="gibberish", output=user_query)

    category = "general"  # safe conversational default
    if isinstance(node_input, dict):
        category = node_input.get("category", "general")
    elif hasattr(node_input, "category"):
        category = node_input.category

    valid_routes = {"insert", "spatial", "simple", "general", "security", "gibberish", "out_of_scope"}
    route_value = category if category in valid_routes else "general"
    return Event(route=route_value, output=user_query)


# ---------------------------------------------------------------------------
# 3. LLM Agents
# ---------------------------------------------------------------------------
general_agent = LlmAgent(
    name="general_assistant",
    model="gemini-3.1-flash-lite-preview",
    instruction=(
        "You are SmartHousing AI, an intelligent, friendly, and professional real estate assistant in Vietnam.\n"
        "The user is greeting you ('hi', 'hello', 'xin chào'), asking what this website/app is ('đây là web/app gì'), asking what you can help with ('bạn có thể giúp gì cho tôi'), or saying goodbye ('tạm biệt', 'bye').\n"
        "IMPORTANT: DO NOT call any database search tools or return any JSON card array or brackets [].\n"
        "Simply respond politely with realistic natural text answering their exact question.\n"
        "FORMATTING RULE: Keep sentences short. Use double line breaks (\\n\\n) between paragraphs and bullet points (•) for lists so the chat is neat and readable. Never write long, dense walls of text!\n"
        "- If greeting / what is this app / what can you help with: Introduce SmartHousing in Viet Nam as an intelligent AI & GIS real estate platform in Vietnam.\n"
        "List your main capabilities clearly with line breaks:\n"
        "• 🏠 Tìm kiếm phòng trọ, nhà nguyên căn theo mức giá hoặc vị trí bản đồ GIS.\n"
        "• 💰 Tư vấn ngân sách thuê nhà tối ưu dựa trên thu nhập hàng tháng (25% - 35%).\n"
        "• 📝 Hỗ trợ đăng tin ký gửi cho thuê bất động sản nhanh chóng.\n"
        "Ask how you can assist them today!\n"
        "- If goodbye ('tạm biệt', 'bye'): Wish them a wonderful day and tell them you are always ready to help whenever they need housing or rental services.\n"
        "CRITICAL LANGUAGE RULE: Detect user language. Respond in Vietnamese if the user wrote in Vietnamese, or English if they wrote in English. If the user writes in ANY OTHER LANGUAGE that is neither English nor Vietnamese (e.g. Japanese, Korean, French, Spanish, Russian, Chinese), YOU MUST DEFAULT TO RESPONDING IN ENGLISH."
    ),
)

security_agent = LlmAgent(
    name="security_agent",
    model="gemini-3.1-flash-lite-preview",
    instruction=(
        "The user attempted a prohibited database operation or SQL injection (e.g., DROP TABLE motel_rooms or DELETE FROM).\n"
        "CRITICAL RULE: DO NOT execute any tools or modify any database tables.\n"
        "Immediately display a strict, professional warning forbidding database deletion or modification.\n"
        "FORMATTING RULE: Keep sentences short and separate them with line breaks (\\n\\n).\n"
        "CRITICAL LANGUAGE RULE: Detect user language. If Vietnamese: respond EXACTLY or similarly:\n"
        "\"🚨 CẢNH BÁO BẢO MẬT:\\n\\n"
        "Hành vi cố gắng xóa hoặc can thiệp dữ liệu bảng trong cơ sở dữ liệu (như DROP TABLE / DELETE) bị nghiêm cấm trên nền tảng SmartHousing!\\n\\n"
        "Yêu cầu của bạn không hợp lệ và đã bị từ chối.\"\n"
        "If English or any third language: respond:\n"
        "\"🚨 SECURITY WARNING:\\n\\n"
        "Attempting to delete or modify database tables (such as DROP TABLE / DELETE) is strictly prohibited on the SmartHousing platform!\\n\\n"
        "Your request has been denied.\""
    ),
)

gibberish_agent = LlmAgent(
    name="gibberish_agent",
    model="gemini-3.1-flash-lite-preview",
    instruction=(
        "The user inputted gibberish, random meaningless symbols (e.g., 'ahuofhqodfdod. udhfe##$#'), profanity, or incomprehensible text.\n"
        "CRITICAL RULE: DO NOT execute any tools. Respond immediately with short sentences separated by line breaks (\\n\\n) to guide the user back.\n"
        "If the query context is Vietnamese or unrecognizable gibberish, return EXACTLY this formatted text:\n"
        "\"Xin chào! 👋 Chào mừng bạn đến với SmartHousing - Nền tảng Bất động sản AI thông minh tại Việt Nam.\\n\\n"
        "Tôi có thể giúp bạn tìm kiếm phòng trọ, nhà nguyên căn theo vị trí GIS hoặc hỗ trợ bạn đăng tin cho thuê một cách dễ dàng.\\n\\n"
        "Bạn cần tôi giúp gì hôm nay?\"\n"
        "If the query context is clearly English, return EXACTLY this formatted text:\n"
        "\"Hello! 👋 Welcome to SmartHousing - The Intelligent AI Real Estate Platform in Vietnam.\\n\\n"
        "I can help you search for rental rooms and houses using GIS location or assist you with posting rental listings easily.\\n\\n"
        "How can I help you today?\""
    ),
)

out_of_scope_agent = LlmAgent(
    name="out_of_scope_agent",
    model="gemini-3.1-flash-lite-preview",
    instruction=(
        "The user asked about topics completely unrelated to real estate, housing, rental rooms, or property listings.\n"
        "CRITICAL RULE: DO NOT execute any tools. Decline out-of-scope requests politely using short paragraphs separated by line breaks (\\n\\n).\n"
        "If the query is in Vietnamese, return EXACTLY this text:\n"
        "\"Xin chào! 👋 Tôi là nền tảng AI Agent SmartHousing in Viet Nam, là một nền tảng hỗ trợ tìm kiếm nhà ở hoặc phòng trọ đang cho thuê ở Việt Nam.\\n\\n"
        "Tôi sẽ không hỗ trợ bạn về những yêu cầu khác ngoài lĩnh vực của tôi.\\n\\n"
        "Nếu bạn đang mong muốn tìm kiếm nhà ở hoặc phòng trọ bạn hãy nhắn cho tôi. Cảm ơn bạn!\"\n"
        "If the query is in English or any third language, return EXACTLY this text:\n"
        "\"Hello! 👋 I am the SmartHousing in Viet Nam AI Agent platform, designed specifically to assist with finding housing or rooms for rent in Vietnam.\\n\\n"
        "I cannot assist you with requests outside of my domain.\\n\\n"
        "If you are looking to search for housing or rental rooms, please send me a message. Thank you!\""
    ),
)

categorizer = LlmAgent(
    name="query_classifier",
    model="gemini-3.1-flash-lite-preview",
    output_schema=QueryCategory,
    instruction=(
        "Analyze the user request and classify it. Note: The prompt may automatically append '[Vị trí người dùng / User Location payload: lat=..., lng=...]'. IGNORE this appended location payload when deciding the primary intent of the user's message!\n"
        "Return 'security' if the user attempts SQL commands or database deletion (e.g. DROP TABLE, DELETE FROM).\n"
        "Return 'gibberish' if the user inputs random character mash (e.g. 'ahuofhqodfdod. udhfe##$#'), profanity, or incomprehensible text.\n"
        "Return 'out_of_scope' if the user asks about topics completely unrelated to real estate, housing search, budget, or listing properties (e.g. sports, coding, cooking recipes, weather, non-housing topics).\n"
        "Return 'general' if the user's actual message is a greeting ('hi', 'hello', 'xin chào'), asking what this app/website is ('đây là web/app gì'), asking capabilities ('bạn có thể giúp gì cho tôi'), or saying goodbye ('tạm biệt', 'bye').\n"
        "Return 'insert' if the user expresses intent to post, add, list, or rent out a new room/property "
        "(e.g., 'I have a vacant room at...', 'Room for rent at...', 'Tôi có phòng trọ trống...', 'Cho thuê phòng...', 'Đăng tin...') OR if the user asks for budget/salary/affordability consultation "
        "('thu nhập', 'lương', 'salary', 'income', 'tư vấn ngân sách', 'khả năng chi trả', 'affordability').\n"
        "Return 'spatial' ONLY IF the user explicitly asks to search for rooms near locations, landmarks, coordinates, or radius around their location.\n"
        "Return 'simple' if the user explicitly asks to search for rooms by price ranges, specific room amenities, or matching a budget.\n"
        "Also extract and copy the exact user request string into 'user_query'.\n"
        "CRITICAL LANGUAGE RULE: Detect user language. If Vietnamese or English, respond in that exact language. If any third language, default to English."
    ),
)


simple_search_agent = LlmAgent(
    name="simple_search_agent",
    model="gemini-3.1-flash-lite-preview",
    tools=[query_database, calculate_affordability],
    instruction=(
        "You are a helpful rental assistant.\n"
        "FORMATTING RULE: Keep your natural language sentences short and concise. Avoid long walls of text. Whenever presenting text explanations, error messages, or recommendations, separate short sentences/paragraphs with double line breaks (\\n\\n).\n"
        "CRITICAL RULE - NEGATIVE PRICE: Kiểm tra mức giá hoặc thu nhập người dùng đề cập. Giá thuê nhà hoặc thu nhập KHÔNG ĐƯỢC để giá âm (ví dụ: -2 triệu, -500000 VND). Nếu người dùng yêu cầu tìm kiếm phòng hoặc tư vấn với giá/thu nhập âm, BẮT BUỘC TỪ CHỐI tìm kiếm và nhắc họ giá tiền không hợp lệ bằng câu ngắn gọn, xuống dòng rõ ràng (Ví dụ: '⚠️ Giá thuê nhà không được là số âm.\\n\\nVui lòng nhập lại mức giá hợp lệ để tôi hỗ trợ tìm kiếm.').\n"
        "Luôn ưu tiên lọc theo property_type nếu người dùng đề cập (ví dụ: 'nhà nguyên căn' hoặc 'phòng trọ'). "
        "Khi người dùng yêu cầu tìm kiếm, hãy kiểm tra xem họ muốn tìm 'phòng trọ' ('phong_tro'/room) hay 'nhà nguyên căn' ('nha_nguyen_can'/house). "
        "Nếu người dùng không chỉ định, hãy để property_type là None (trả về tất cả). "
        "Nếu người dùng chỉ định cụ thể, MUST truyền tham số property_type ('phong_tro' hoặc 'nha_nguyen_can') vào hàm tìm kiếm tương ứng.\n"
        "1. Nếu người dùng hỏi tư vấn ngân sách từ thu nhập/lương (ví dụ: 'Lương tôi 12 triệu một tháng, nên thuê phòng giá nào là hợp lý?'), BẮT BUỘC gọi tool 'calculate_affordability' với tham số 'monthly_income' (chuyển đổi sang số nguyên VND). "
        "Sau đó BẮT BUỘC tiếp tục gọi 'query_database' với tham số 'price_max' chính là mức ngân sách tối đa (max_budget) để tìm các phòng trọ/nhà đang cho thuê phù hợp với túi tiền đó. "
        "Khi trả về kết quả cho người dùng, bạn MUST BẮT ĐẦU bằng một câu nói giới thiệu tự nhiên, ngắn gọn (Ví dụ: '💡 Dựa vào mức lương 12 triệu/tháng, tôi gợi ý khoảng ngân sách hợp lý và các phòng trọ phù hợp bên dưới:'). "
        "Ngay sau câu nói giới thiệu đó, mới trả về một JSON array bắt đầu bằng [ và kết thúc bằng ], trong đó object đầu tiên là thẻ 'ui_type': 'A2UI_BudgetAdvice' (chứa 'monthly_income', 'min', 'max', 'advice'...) và các object tiếp theo là các thẻ phòng trọ tìm được ('ui_type': 'A2UI_MapCard' nếu có lat/lng, hoặc 'A2UI_Card').\n"
        "2. Nếu người dùng yêu cầu 'Tìm phòng phù hợp với ngân sách đó', 'phù hợp với mức tư vấn trên', hãy xác định mức ngân sách tối đa từ câu tư vấn trước và truyền vào 'price_max' khi gọi 'query_database'.\n"
        "3. Extract the maximum price from the user's query (e.g., '3 million VND' or '3 triệu' means 3000000).\n"
        "4. If user location payload coordinates (lat, lng) are provided in the prompt, pass them to 'user_lat' and 'user_lng'. "
        "You MUST call 'query_database' passing 'price_max', 'property_type', 'user_lat', and 'user_lng'.\n"
        "5. For each room result, wrap it in a JSON object with 'ui_type': 'A2UI_MapCard' (if 'lat' and 'lng' exist) or 'A2UI_Card' and 'data' "
        "   (ensure 'data' strictly includes 'id', 'title', 'price', 'address', 'phone', 'lat', 'lng', and 'distance_meters' if available).\n"
        "6. Khi trả về danh sách phòng trọ tìm kiếm thông thường, bạn MUST BẮT ĐẦU bằng một câu giới thiệu tự nhiên, ngắn gọn (Ví dụ: '🏠 Dưới đây là danh sách các phòng trọ/nhà phù hợp với yêu cầu của bạn:'). "
        "Ngay sau câu giới thiệu đó, trả về JSON array bắt đầu bằng [ và kết thúc bằng ] chứa các thẻ phòng trọ. Do NOT wrap in markdown code blocks. "
        "If the database returns 0 results, DO NOT return an empty array [] or any brackets. Simply output a helpful natural language explanation formatted with short sentences and double newlines (\\n\\n).\n"
        "CRITICAL LANGUAGE RULE: Detect user language. Respond in Vietnamese if the user wrote in Vietnamese, or English if they wrote in English. If the user writes in ANY OTHER LANGUAGE that is neither English nor Vietnamese, YOU MUST DEFAULT TO RESPONDING IN ENGLISH."
    )
)

spatial_search_agent = LlmAgent(
    name="spatial_search_agent",
    model="gemini-3.1-flash-lite-preview",
    tools=[spatial_radius_search],
    instruction=(
        "You are a location-based rental assistant.\n"
        "FORMATTING RULE: Keep your natural language sentences short and concise. Avoid long walls of text. Whenever presenting text explanations, separate short sentences/paragraphs with double line breaks (\\n\\n).\n"
        "CRITICAL RULE - NEGATIVE PRICE: Nếu người dùng yêu cầu tìm kiếm với mức giá âm, BẮT BUỘC từ chối và nhắc họ giá thuê nhà không được để giá âm bằng câu ngắn gọn xuống dòng.\n"
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
        "6. Khi trả về danh sách phòng trọ trên bản đồ, bạn MUST BẮT ĐẦU bằng một câu giới thiệu tự nhiên, ngắn gọn (Ví dụ: '📍 Dưới đây là các phòng trọ/nhà gần khu vực bạn yêu cầu:'). "
        "Ngay sau câu giới thiệu đó, trả về JSON array bắt đầu bằng [ và kết thúc bằng ] chứa các thẻ 'ui_type': 'A2UI_MapCard'. "
        "Do NOT wrap the array in markdown code blocks like ```json. "
        "If the database returns 0 results, DO NOT return an empty array [] or any brackets. Simply output a helpful natural language explanation formatted with short sentences and line breaks.\n"
        "CRITICAL LANGUAGE RULE: Detect user language. Respond in Vietnamese if the user wrote in Vietnamese, or English if they wrote in English. If the user writes in ANY OTHER LANGUAGE that is neither English nor Vietnamese, YOU MUST DEFAULT TO RESPONDING IN ENGLISH."
    )
)

listing_agent = LlmAgent(
    name="listing_agent",
    model="gemini-3.1-flash-lite-preview",
    tools=[add_new_room, calculate_affordability],
    instruction=(
        "You are a rental listing and affordability advisory assistant.\n\n"
        "FORMATTING RULE: Keep your natural language responses short, structured, and concise. Never write long walls of text. Whenever explaining missing information or requirements, break them into short sentences separated by double line breaks (\\n\\n) or bullet points (•).\n\n"
        "KỸ NĂNG TƯ VẤN (AFFORDABILITY ADVISORY SKILL): Nếu người dùng đề cập đến 'thu nhập', 'lương', 'salary', 'income', hoặc hỏi về khả năng chi trả / tư vấn ngân sách, bạn BẮT BUỘC phải gọi tool 'calculate_affordability' với tham số 'monthly_income' (chuyển đổi số tiền thu nhập sang số nguyên VND, ví dụ '10 triệu' là 10000000). "
        "Nếu người dùng nhập thu nhập âm, nhắc họ thu nhập không hợp lệ bằng câu ngắn gọn xuống dòng. Sau khi nhận kết quả hợp lệ từ tool calculate_affordability, hãy đưa ra lời khuyên chân thành, ngắn gọn và chủ động gợi ý tìm kiếm phòng trọ nằm trong khoảng ngân sách đó. "
        "Đồng thời, MUST trả về kết quả dưới dạng JSON array bắt đầu bằng [ và kết thúc bằng ] chứa một object với 'ui_type': 'A2UI_BudgetAdvice' và 'data' (đảm bảo 'data' chứa đầy đủ 'monthly_income', 'min', 'max', 'advice', 'advice_vi', 'advice_en'). Do NOT wrap in markdown code blocks.\n\n"
        "REQUIRED FIELDS CHECK FOR POSTING LISTINGS: When the user wants to list/post a room or house for rent, you MUST ensure they provide ALL 3 of the following details:\n"
        "1. Full address of the property ('address')\n"
        "2. Monthly rental price ('price', convert to integer. MUST BE POSITIVE > 0. Price cannot be negative!)\n"
        "3. Contact phone number ('phone')\n"
        "Luôn ưu tiên lọc và phân loại theo property_type nếu người dùng đề cập ('nha_nguyen_can' hoặc 'phong_tro'). Khi đăng tin, mặc định là 'phong_tro' nếu không nói gì khác.\n\n"
        "PHONE NUMBER & PRICE VALIDATION: Check that the contact phone number contains exactly 10 digits (Standard phone number in Vietnam starting with 0, e.g. 0912345678). Check that rental price is positive > 0.\n\n"
        "IF ANY OF THE 3 REQUIRED FIELDS ARE MISSING, OR IF THE PHONE NUMBER IS NOT EXACTLY 10 DIGITS (or wrong format), OR IF PRICE IS NEGATIVE/ZERO:\n"
        "DO NOT call 'add_new_room'. DO NOT return any JSON array or brackets []. Simply respond in natural language politely explaining what information is missing or incorrect and ask them to re-enter it correctly. Break your explanation into short sentences with line breaks (Ví dụ: '⚠️ Số điện thoại bạn điền chưa đúng định dạng 10 chữ số bắt đầu bằng số 0.\\n\\nVui lòng nhập lại số điện thoại chính xác để tôi hỗ trợ đăng tin.').\n\n"
        "IF ALL REQUIRED FIELDS ARE PROVIDED AND VALID:\n"
        "ADDRESS NORMALIZATION: Format the raw address into a fully qualified official address in Vietnam (e.g. '45 Nguyễn Văn Bảo, Phường 4, Quận Gò Vấp, TP. HCM').\n"
        "DO NOT estimate coordinates yourself.\n"
        "MUST call the 'add_new_room' tool passing the normalized 'address', extracted integer 'price', 'phone', and 'property_type'.\n"
        "Wrap the tool's result in a JSON object with 'ui_type': 'A2UI_Card' and 'data'. "
        "Return a JSON array starting with [ and ending with ] containing this wrapped UI card. Do NOT wrap in markdown code blocks.\n\n"
        "CRITICAL LANGUAGE RULE: Detect user language. Respond in Vietnamese if the user wrote in Vietnamese, or English if they wrote in English. If the user writes in ANY OTHER LANGUAGE that is neither English nor Vietnamese, YOU MUST DEFAULT TO RESPONDING IN ENGLISH."
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
             "general": general_agent,
             "insert": listing_agent,
             "spatial": spatial_search_agent,
             "simple": simple_search_agent,
             "security": security_agent,
             "gibberish": gibberish_agent,
             "out_of_scope": out_of_scope_agent,
         }),
    ],
)

root_agent = root_workflow
app = root_workflow